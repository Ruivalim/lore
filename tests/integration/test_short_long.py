"""Resposta curta e completa, e o campo summary dos documentos.

O que quebra: agente que embrulha o JSON ou nem manda JSON, curta sem
citação, resumo com quebra de linha ou grande demais no front matter,
segredo escondido no resumo, e a CLI escondendo a resposta quando não há curta.
"""

import json
import os
import shutil

import pytest

from lore import index as index_mod
from lore import repo as repo_mod
from lore.answer import ask, parse_short_long
from lore.cli import main
from lore.models import SUMMARY_MAX, parse_doc, validate
from lore.research import (
    RemoteModel,
    WebSearch,
    clean_summary,
    extract_summary,
    research,
)


@pytest.fixture()
def repo(tmp_path):
    root = str(tmp_path / "repo")
    os.makedirs(os.path.join(root, "knowledge"))
    os.makedirs(os.path.join(root, "drafts"))
    os.makedirs(os.path.join(root, ".lore"))
    for name in os.listdir("tests/fixtures/corpus"):
        shutil.copy(os.path.join("tests/fixtures/corpus", name),
                    os.path.join(root, "knowledge", name))
    handle = repo_mod.Repo(root)
    index_mod.build(handle)
    return handle


CITE_FILE = "wireguard-split-dns.md"


def _fake_agent(monkeypatch, response):
    calls = []

    def fake_complete(self, prompt, system=""):
        calls.append(prompt)
        return response

    monkeypatch.setattr("lore.agents.Agent.complete", fake_complete)
    return calls


# --- parse_short_long ---------------------------------------------------------

@pytest.mark.parametrize("raw", [
    '{"short": "curta", "long": "longa"}',
    '```json\n{"short": "curta", "long": "longa"}\n```',
    'Aqui está:\n{"short": "curta", "long": "longa"}\nfim',
])
def test_parse_short_long_accepts_wrapped_json(raw):
    assert parse_short_long(raw) == ("curta", "longa")


@pytest.mark.parametrize("raw", [
    "texto corrido sem JSON",
    '{"short": "só curta"}',
    '{"short": "x", "long": "   "}',
    '{"short": "x", "long": 3}',
    '{quebrado: ',
    '[1, 2]',
])
def test_parse_short_long_falls_back_to_everything_as_long(raw):
    assert parse_short_long(raw) == ("", raw.strip())


def test_parse_short_long_ignores_non_string_short():
    assert parse_short_long('{"short": ["a"], "long": "longa"}') == ("", "longa")


# --- ask ----------------------------------------------------------------------

def test_ask_returns_short_and_long_with_citations(repo, monkeypatch):
    calls = _fake_agent(monkeypatch, json.dumps({
        "short": f"Use DNS por domínio no túnel [{CITE_FILE}#Procedimento].",
        "long": f"Passo a passo completo [{CITE_FILE}#Procedimento].",
    }))
    answer = ask(repo, "split DNS WireGuard", extractive=False)
    assert '"short"' in calls[0] and '"long"' in calls[0]
    assert answer.short.startswith("Use DNS por domínio")
    assert answer.text.startswith("Passo a passo completo")


def test_ask_drops_short_without_citation_but_keeps_long(repo, monkeypatch):
    _fake_agent(monkeypatch, json.dumps({
        "short": "Use DNS por domínio.",
        "long": f"Completa [{CITE_FILE}#Procedimento].",
    }))
    answer = ask(repo, "split DNS WireGuard", extractive=False)
    assert answer.short == ""
    assert answer.text.startswith("Completa")


def test_ask_plain_text_agent_still_answers(repo, monkeypatch):
    _fake_agent(monkeypatch, f"Resposta corrida [{CITE_FILE}#Procedimento].")
    answer = ask(repo, "split DNS WireGuard", extractive=False)
    assert answer.short == ""
    assert answer.text.startswith("Resposta corrida")


def _add_summary(repo, doc_file, summary, status=None):
    path = os.path.join(repo.root, "knowledge", doc_file)
    text = open(path, encoding="utf-8").read()
    text = text.replace("\ntype:", f"\nsummary: {summary}\ntype:", 1)
    if status:
        text = text.replace("status: verified", f"status: {status}", 1)
    open(path, "w", encoding="utf-8").write(text)
    index_mod.build(repo)


def test_extractive_short_comes_from_verified_summary(repo):
    _add_summary(repo, CITE_FILE, "Split DNS: DNS por domínio dentro do túnel.")
    answer = ask(repo, "split DNS WireGuard", extractive=True)
    assert answer.short.startswith("Split DNS: DNS por domínio dentro do túnel.")
    assert CITE_FILE in answer.short


def test_extractive_without_summary_has_no_short(repo):
    answer = ask(repo, "split DNS WireGuard", extractive=True)
    assert answer.short == ""


# --- CLI ----------------------------------------------------------------------

def test_cli_prints_short_by_default_and_full_on_request(repo, monkeypatch, capsys):
    _fake_agent(monkeypatch, json.dumps({
        "short": f"Curta [{CITE_FILE}#Procedimento].",
        "long": f"Completa e longa [{CITE_FILE}#Procedimento].",
    }))
    assert main(["--root", repo.root, "ask", "split DNS WireGuard"]) == 0
    out = capsys.readouterr().out
    assert "Curta" in out and "Completa e longa" not in out
    assert "lore ask --full" in out

    assert main(["--root", repo.root, "ask", "split DNS WireGuard", "--full"]) == 0
    out = capsys.readouterr().out
    assert "Completa e longa" in out and "lore ask --full" not in out

    assert main(["--root", repo.root, "--json", "ask", "split DNS WireGuard"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["short"].startswith("Curta")
    assert payload["text"].startswith("Completa e longa")


def test_cli_without_short_prints_full_and_no_hint(repo, monkeypatch, capsys):
    _fake_agent(monkeypatch, f"Só completa [{CITE_FILE}#Procedimento].")
    assert main(["--root", repo.root, "ask", "split DNS WireGuard"]) == 0
    out = capsys.readouterr().out
    assert "Só completa" in out and "--full" not in out


# --- summary no front matter --------------------------------------------------

def test_summary_validation():
    base = {"id": "x", "title": "X", "type": "note", "status": "draft", "tags": ["a"],
            "created_at": "2026-01-01", "updated_at": "2026-01-01", "sources": []}
    body = "# X\n\nTexto.\n"
    assert validate({**base, "summary": "ok"}, body) == []
    assert validate({**base, "summary": "  "}, body)
    assert validate({**base, "summary": 3}, body)
    assert validate({**base, "summary": "x" * (SUMMARY_MAX + 1)}, body)


def test_clean_summary_one_line_and_bounded():
    assert clean_summary("linha um\n\nlinha   dois") == "linha um linha dois"
    long = clean_summary("palavra " * 200)
    assert len(long) <= SUMMARY_MAX and long.endswith("…")


def test_extract_summary_only_from_leading_section():
    summary, rest = extract_summary("## Resumo\nCurto e direto.\n\n## Resposta\nLonga.")
    assert summary == "Curto e direto."
    assert rest.startswith("## Resposta")
    assert extract_summary("## Resposta\nLonga.\n## Resumo\nx") == (
        "", "## Resposta\nLonga.\n## Resumo\nx")
    assert extract_summary("## Resumo\n\n## Resposta\nx")[0] == ""


class _NoWeb(WebSearch):
    def search(self, query, max_results=5):
        return []


class _Model(RemoteModel):
    def __init__(self, text):
        self.text = text

    def complete(self, prompt):
        return self.text


def test_web_research_draft_gets_summary_and_round_trips(repo):
    response = ("## Resumo\nUse X: ele resolve\no problema.\n\n"
                "## Resposta\nProvisória e longa.\n\n## Incertezas\nNenhuma.")
    result = research(repo, "pergunta nova", web=_NoWeb(), model=_Model(response))
    assert result.ok and result.summary == "Use X: ele resolve o problema."
    doc = parse_doc(open(result.draft_path, encoding="utf-8").read(), result.draft_path)
    assert doc.valid, doc.errors
    assert doc.front["summary"] == "Use X: ele resolve o problema."
    assert "## Resumo" not in doc.body and "Provisória e longa" in doc.body


def test_web_research_without_summary_section_has_no_summary_key(repo):
    result = research(repo, "outra pergunta", web=_NoWeb(), model=_Model("Só resposta."))
    doc = parse_doc(open(result.draft_path, encoding="utf-8").read(), result.draft_path)
    assert doc.valid and "summary" not in doc.front and result.summary == ""


def test_claude_summary_with_secret_blocks_draft(repo):
    from lore.claude_cli import ClaudeResult
    from lore.research import research_agent

    class Agent:
        def run(self, question, local_context):
            return ClaudeResult(answer="ok", summary="token ghp_abcdefghij1234567890abcd")

    result = research_agent(repo, "pergunta", agent=Agent())
    assert not result.ok and "segredo" in result.blocked
    assert os.listdir(os.path.join(repo.root, "drafts")) == []


def test_claude_summary_goes_to_front_matter(repo):
    from lore.claude_cli import ClaudeResult
    from lore.research import research_agent

    class Agent:
        def run(self, question, local_context):
            return ClaudeResult(answer="## Resposta (provisória)\nLonga.",
                                summary="Curta\ne direta.")

    result = research_agent(repo, "pergunta claude", agent=Agent())
    doc = parse_doc(open(result.draft_path, encoding="utf-8").read(), result.draft_path)
    assert doc.front["summary"] == "Curta e direta."


def test_terminal_output_uses_paths_relative_to_acervo(repo, monkeypatch, capsys):
    _fake_agent(monkeypatch, json.dumps({
        "short": f"Curta [{repo.root}/knowledge/{CITE_FILE}#Procedimento].",
        "long": f"Longa [{repo.root}/knowledge/{CITE_FILE}#Procedimento].",
    }))
    assert main(["--root", repo.root, "ask", "split DNS WireGuard"]) == 0
    out = capsys.readouterr().out
    assert f"[knowledge/{CITE_FILE}#Procedimento]" in out and repo.root not in out
    assert main(["--root", repo.root, "--json", "ask", "split DNS WireGuard"]) == 0
    assert repo.root in json.loads(capsys.readouterr().out)["short"]
