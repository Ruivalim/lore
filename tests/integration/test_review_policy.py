"""[review]: aprovação automática por origem, sempre rastreável.

O que quebra: auto-if-clean deixando passar rascunho sujo, política inválida
derrubando o import, aprovado sem revisão sumindo da fila, confirmação humana
virando reaprovação, e o commit automático perdendo o arquivo movido.
"""

import json
import os
import subprocess

import pytest

from lore import repo as repo_mod
from lore import review as review_mod
from lore.cli import main
from lore.models import Doc, parse_doc, transition
from lore.research import RemoteModel, Source, WebSearch, research

CLEAN_BODY_RESPONSE = (
    "## Resumo\nUse X [fonte 1].\n\n"
    "## Resposta\nUse X conforme a documentação [fonte 1].\n"
)


@pytest.fixture()
def repo(tmp_path):
    root = tmp_path / "acervo"
    for name in ("knowledge", "drafts", "archive", ".lore"):
        (root / name).mkdir(parents=True)
    return repo_mod.Repo(str(root))


def _config(repo, text):
    with open(os.path.join(repo.root, ".lore", "config.toml"), "w", encoding="utf-8") as h:
        h.write(text)


class _Web(WebSearch):
    def __init__(self, urls):
        self.urls = urls

    def search(self, query, max_results=5):
        return [Source(url=u, title=u, accessed_at="2026-11-05") for u in self.urls]


class _Model(RemoteModel):
    def __init__(self, text):
        self.text = text

    def complete(self, prompt):
        return self.text


def _draft(repo, response, urls=("https://docs.example/x",), question="pergunta x"):
    result = research(repo, question, web=_Web(list(urls)), model=_Model(response))
    assert result.ok, result.error
    return result, os.path.splitext(os.path.basename(result.draft_path))[0]


@pytest.fixture(autouse=True)
def pages(monkeypatch):
    monkeypatch.setattr("lore.research.fetch_page", lambda url: "conteúdo da página")


# --- política e transição -----------------------------------------------------

def test_transition_still_refuses_verified_without_human_or_auto_policy():
    doc = Doc(front={"status": "draft"}, body="")
    assert transition(doc, "verified") != []
    assert transition(doc, "verified", policy="human") != []
    assert transition(Doc(front={"status": "draft"}, body=""), "verified",
                      policy="auto") == []


def test_policy_for_defaults_and_rejects_bad_values():
    assert review_mod.policy_for({}, "research") == "human"
    assert review_mod.policy_for({"review": {"import": "auto"}}, "import") == "auto"
    with pytest.raises(ValueError, match="review.research inválido"):
        review_mod.policy_for({"review": {"research": "sempre"}}, "research")
    with pytest.raises(ValueError):
        review_mod.policy_for({}, "new")


def test_human_policy_keeps_draft(repo):
    _, doc_id = _draft(repo, CLEAN_BODY_RESPONSE)
    out = review_mod.apply_policy(repo, {}, doc_id, "research")
    assert out == {"policy": "human", "approved": False, "path": "", "reasons": []}
    assert repo_mod.find_by_id(repo, doc_id).status == "draft"


def test_auto_if_clean_approves_clean_research_and_marks_auto(repo):
    _, doc_id = _draft(repo, CLEAN_BODY_RESPONSE)
    cfg = {"review": {"research": "auto-if-clean"}}
    out = review_mod.apply_policy(repo, cfg, doc_id, "research")
    assert out["approved"], out
    doc = repo_mod.find_by_id(repo, doc_id)
    assert doc.status == "verified" and doc.front["reviewed_by"] == "auto"
    assert os.path.dirname(doc.path).endswith("knowledge")


@pytest.mark.parametrize("response, urls, discarded, reason", [
    (CLEAN_BODY_RESPONSE, (), [], "nenhuma fonte web"),
    ("## Resumo\nCurto.\n\n## Resposta\n" + "Afirmação longa sem nenhuma fonte "
     "marcada que passa de sessenta caracteres.\n", ("https://d.example",), [],
     "sem fonte"),
    (CLEAN_BODY_RESPONSE, ("https://d.example",),
     ["https://mal.example (injection descartada: ignore previous)"], "injection"),
])
def test_auto_if_clean_keeps_dirty_research(repo, response, urls, discarded, reason):
    _, doc_id = _draft(repo, response, urls)
    cfg = {"review": {"research": "auto-if-clean"}}
    out = review_mod.apply_policy(repo, cfg, doc_id, "research", discarded)
    assert not out["approved"]
    assert any(reason in item for item in out["reasons"]), out["reasons"]
    assert repo_mod.find_by_id(repo, doc_id).status == "draft"


def test_auto_if_clean_blocks_on_conflict_even_for_import(repo):
    existing = (
        "---\nid: velho\ntitle: Velho\ntype: howto\nstatus: verified\n"
        "tags:\n  - dns\n  - wireguard\ncreated_at: 2026-01-01\nupdated_at: 2026-01-01\n"
        "verified_at: 2026-01-01\nsources:\n  - kind: personal\n    description: x\n"
        "---\n\n# Velho\n\nTexto.\n")
    with open(os.path.join(repo.root, "knowledge", "velho.md"), "w", encoding="utf-8") as h:
        h.write(existing)
    new = existing.replace("id: velho", "id: novo").replace("status: verified",
                                                           "status: draft")
    new = new.replace("verified_at: 2026-01-01\n", "")
    with open(os.path.join(repo.root, "drafts", "novo.md"), "w", encoding="utf-8") as h:
        h.write(new)
    out = review_mod.apply_policy(repo, {"review": {"import": "auto-if-clean"}},
                                  "novo", "import")
    assert not out["approved"] and "conflito" in out["reasons"][0]
    # auto puro não olha conflito
    out = review_mod.apply_policy(repo, {"review": {"import": "auto"}}, "novo", "import")
    assert out["approved"]


def test_auto_approved_stays_in_queue_until_human_confirms(repo):
    _, doc_id = _draft(repo, CLEAN_BODY_RESPONSE)
    review_mod.apply_policy(repo, {"review": {"research": "auto"}}, doc_id, "research")
    queue = {item[0]: item[2] for item in review_mod.queue(repo)}
    assert "sem revisão" in queue[doc_id]

    with pytest.raises(ValueError, match="--human"):
        review_mod.approve(repo, doc_id)
    review_mod.approve(repo, doc_id, human=True)
    doc = repo_mod.find_by_id(repo, doc_id)
    assert doc.status == "verified" and doc.front["reviewed_by"] == "human"
    assert doc_id not in {item[0] for item in review_mod.queue(repo)}


def test_human_approve_of_draft_records_reviewer(repo):
    _, doc_id = _draft(repo, CLEAN_BODY_RESPONSE)
    review_mod.approve(repo, doc_id, human=True)
    assert repo_mod.find_by_id(repo, doc_id).front["reviewed_by"] == "human"


def test_reviewed_by_must_be_known_value(repo):
    _, doc_id = _draft(repo, CLEAN_BODY_RESPONSE)
    doc = repo_mod.find_by_id(repo, doc_id)
    text = open(doc.path, encoding="utf-8").read().replace(
        "\ntype:", "\nreviewed_by: robo\ntype:", 1)
    assert any("reviewed_by" in err for err in parse_doc(text, doc.path).errors)


# --- CLI ----------------------------------------------------------------------

def _git(root, *args):
    return subprocess.run(["git", "-C", root, *args], capture_output=True,
                          text=True, check=True).stdout


def test_cli_import_auto_approves_and_commits_final_path(repo, tmp_path, monkeypatch,
                                                          capsys):
    _git(repo.root, "init", "-q")
    with open(os.path.join(repo.root, ".gitignore"), "w", encoding="utf-8") as h:
        h.write(".lore/\n")  # como o lore init deixa
    _git(repo.root, "config", "user.email", "t@t")
    _git(repo.root, "config", "user.name", "t")
    _config(repo, '[review]\nimport = "auto"\n[git]\nauto_commit = true\n')
    source = tmp_path / "nota.md"
    source.write_text("# Nota\n\nTexto meu.\n", encoding="utf-8")
    monkeypatch.setattr("lore.agents.Agent.complete", lambda self, p, system="": json.dumps(
        {"title": "Nota minha", "type": "note", "tags": ["x"], "summary": "Resumo."}))

    assert main(["--root", repo.root, "--json", "import", str(source)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "verified" and payload["review"]["approved"]
    assert payload["path"].endswith(os.path.join("knowledge", "nota-minha.md"))
    assert _git(repo.root, "show", "--name-only", "--format=", "HEAD").split() == [
        "knowledge/nota-minha.md"]
    assert _git(repo.root, "status", "--porcelain") == "?? .gitignore\n"


def test_cli_import_with_bad_policy_keeps_draft_and_says_why(repo, tmp_path,
                                                              monkeypatch, capsys):
    _config(repo, '[review]\nimport = "sempre"\n')
    source = tmp_path / "nota.md"
    source.write_text("# Nota\n\nTexto.\n", encoding="utf-8")
    monkeypatch.setattr("lore.agents.Agent.complete", lambda self, p, system="": json.dumps(
        {"title": "Nota", "type": "note", "tags": ["x"]}))
    assert main(["--root", repo.root, "import", str(source)]) == 0
    out = capsys.readouterr().out
    assert "ficou em rascunho" in out and "review.import inválido" in out
    assert os.path.isfile(os.path.join(repo.root, "drafts", "nota.md"))


def test_cli_research_auto_if_clean_reports_reasons(repo, monkeypatch, capsys):
    _config(repo, '[research]\nenabled = true\n[review]\nresearch = "auto-if-clean"\n')
    monkeypatch.setattr("lore.research.DuckDuckGoWebSearch.search",
                        lambda *a, **k: [])
    monkeypatch.setattr("lore.agents.Agent.complete",
                        lambda self, p, system="": CLEAN_BODY_RESPONSE)
    assert main(["--root", repo.root, "--json", "ask", "pergunta sem base", "--yes"]) == 0
    payload = json.loads(capsys.readouterr().out)
    review = payload["research"]["review"]
    assert not review["approved"] and "nenhuma fonte web" in review["reasons"]


def test_doctor_flags_invalid_review_policy(repo, capsys):
    _config(repo, '[review]\nresearch = "talvez"\n')
    assert main(["--root", repo.root, "--json", "doctor"]) == 1
    problems = json.loads(capsys.readouterr().out)["problems"]
    assert any("review.research inválido" in p for p in problems)


# --- reativar stale -----------------------------------------------------------

def _stale_doc(repo, verified_at="2026-01-01", review_after="2026-04-01",
               doc_id="velho-stale"):
    text = (
        f"---\nid: {doc_id}\ntitle: Velho\ntype: howto\nstatus: stale\n"
        "reviewed_by: auto\ntags:\n  - x\ncreated_at: 2026-01-01\n"
        f"updated_at: 2026-01-01\nverified_at: {verified_at}\n"
        + (f"review_after: {review_after}\n" if review_after else "")
        + "sources:\n  - kind: personal\n    description: x\n---\n\n# Velho\n\nTexto.\n")
    path = os.path.join(repo.root, "knowledge", f"{doc_id}.md")
    with open(path, "w", encoding="utf-8") as h:
        h.write(text)
    return path


def test_human_reverifies_stale_in_place_and_shifts_review_after(repo, monkeypatch):
    monkeypatch.setattr(review_mod, "_today", lambda: "2026-11-05")
    path = _stale_doc(repo)
    assert review_mod.approve(repo, "velho-stale", human=True) == path
    doc = repo_mod.find_by_id(repo, "velho-stale")
    assert doc.status == "verified" and doc.path == path
    assert doc.front["verified_at"] == "2026-11-05"
    assert doc.front["reviewed_by"] == "human"
    assert doc.front["review_after"] == "2027-02-03"  # mesmos 90 dias, a partir de hoje
    assert "velho-stale" not in {item[0] for item in review_mod.queue(repo)}


@pytest.mark.parametrize("verified_at, review_after, expected", [
    ("2026-01-01", "2027-01-01", "2027-01-01"),   # ainda no futuro: não mexe
    ("2026-01-01", None, None),                   # sem review_after: não inventa
    ("2026-05-01", "2026-04-01", "2026-04-01"),   # intervalo negativo: não repete
])
def test_reverify_review_after_edge_cases(repo, monkeypatch, verified_at,
                                          review_after, expected):
    monkeypatch.setattr(review_mod, "_today", lambda: "2026-11-05")
    _stale_doc(repo, verified_at, review_after)
    review_mod.approve(repo, "velho-stale", human=True)
    assert repo_mod.find_by_id(repo, "velho-stale").front.get("review_after") == expected


def test_stale_is_never_reactivated_without_human(repo):
    _stale_doc(repo)
    with pytest.raises(ValueError, match="--human"):
        review_mod.approve(repo, "velho-stale", policy="auto")
    assert repo_mod.find_by_id(repo, "velho-stale").status == "stale"


def test_cli_approve_stale_and_archived_still_refused(repo, capsys):
    _stale_doc(repo)
    assert main(["--root", repo.root, "approve", "velho-stale"]) == 1
    assert "--human" in capsys.readouterr().err
    assert main(["--root", repo.root, "approve", "velho-stale", "--human"]) == 0
    capsys.readouterr()
    review_mod.archive(repo, "velho-stale", human=True)
    assert main(["--root", repo.root, "approve", "velho-stale", "--human"]) == 1
    assert "draft ou stale" in capsys.readouterr().err
