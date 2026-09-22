"""Fase 5: revisão, promoção e ciclo completo de aprendizado (§20)."""

import json
import os
import shutil

import pytest

from lore import index as index_mod
from lore import repo as repo_mod
from lore import review as review_mod
from lore.answer import ask
from lore.cli import main
from lore.models import parse_doc


@pytest.fixture()
def repo(tmp_path):
    root = str(tmp_path / "repo")
    for dirname in ("knowledge", "drafts", "archive"):
        os.makedirs(os.path.join(root, dirname))
    for name in os.listdir("tests/fixtures/corpus"):
        shutil.copy(os.path.join("tests/fixtures/corpus", name),
                    os.path.join(root, "knowledge", name))
    with open(os.path.join(root, "drafts", "novo.md"), "w",
              encoding="utf-8") as handle:
        handle.write(
            "---\nid: novo-guia\ntitle: Novo guia\ntype: howto\nstatus: draft\n"
            "tags:\n  - linux\n  - networking\ncreated_at: 2026-01-01\n"
            "updated_at: 2026-01-01\nverified_at: null\nsources:\n"
            "  - kind: personal\n    description: lab\n---\n\n"
            "# Novo guia\n\n## Procedimento\n\nPasso um, passo dois.\n")
    handle_repo = repo_mod.Repo(root)
    index_mod.build(handle_repo)
    return handle_repo


def run_cli(root, *argv):
    return main(["--root", root, *argv])


def test_queue_lists_draft(repo):
    items = review_mod.queue(repo)
    assert any(doc_id == "novo-guia" for doc_id, _, _ in items)


def test_approve_requires_human(repo):
    with pytest.raises(ValueError, match="humana"):
        review_mod.approve(repo, "novo-guia", human=False)
    assert repo_mod.find_by_id(repo, "novo-guia").status == "draft"


def test_approve_promotes_and_reindexes(repo):
    dest = review_mod.approve(repo, "novo-guia", human=True)
    assert "knowledge" in dest
    doc = repo_mod.find_by_id(repo, "novo-guia")
    assert doc.status == "verified"
    assert doc.front["verified_at"]
    answer = ask(repo, "passo um passo dois")
    assert answer.coverage == "sufficient"


def test_reject_needs_reason_and_human(repo):
    with pytest.raises(ValueError, match="motivo"):
        review_mod.reject(repo, "novo-guia", "", human=True)
    with pytest.raises(ValueError, match="humana"):
        review_mod.reject(repo, "novo-guia", "ruim", human=False)
    dest = review_mod.reject(repo, "novo-guia", "fora de escopo", human=True)
    assert "archive" in dest
    assert repo_mod.find_by_id(repo, "novo-guia").status == "archived"


def test_stale_and_archive(repo):
    review_mod.mark_stale(repo, "restic-x99", human=True)
    assert repo_mod.find_by_id(repo, "restic-x99").status == "stale"
    dest = review_mod.archive(repo, "restic-x99", human=True)
    assert "archive" in dest
    with pytest.raises(ValueError):
        review_mod.approve(repo, "restic-x99", human=True)


def test_detail_shows_sources_and_conflicts(repo):
    info = review_mod.detail(repo, "novo-guia")
    assert info["front"]["status"] == "draft"
    assert info["possible_conflicts"]  # compartilha linux+networking
    assert any("wireguard-split-dns" in item for item in info["possible_conflicts"])


def test_edit_noop_keeps_valid(repo, monkeypatch):
    monkeypatch.setenv("EDITOR", "true")
    assert review_mod.edit(repo, "novo-guia").endswith("novo.md")


def test_edit_failure_reported(repo, monkeypatch):
    monkeypatch.setenv("EDITOR", "false")
    with pytest.raises(RuntimeError):
        review_mod.edit(repo, "novo-guia")


def test_cli_review_queue_and_approve(repo, capsys):
    assert run_cli(repo.root, "review") == 0
    assert "novo-guia" in capsys.readouterr().out
    assert run_cli(repo.root, "approve", "novo-guia") == 1  # sem --human
    assert run_cli(repo.root, "approve", "novo-guia", "--human") == 0
    assert "knowledge" in capsys.readouterr().out


def test_learning_cycle(tmp_path, monkeypatch, capsys):
    """Ciclo §20 ponta a ponta em repo temporário."""
    from lore.research import RemoteModel, Source, WebSearch, research

    root = str(tmp_path / "ciclo")
    os.makedirs(os.path.join(root, "knowledge"))
    doc = ("---\nid: ciclo-dns\ntitle: DNS no ciclo\ntype: howto\nstatus: verified\n"
           "tags:\n  - rede\ncreated_at: 2026-01-01\nupdated_at: 2026-01-01\n"
           "verified_at: 2026-01-01\nsources:\n  - kind: personal\n"
           "    description: lab\n---\n\n# DNS no ciclo\n\n## Procedimento\n\n"
           "Configure o resolved com o DNS do túnel.\n")
    src = tmp_path / "doc.md"
    src.write_text(doc, encoding="utf-8")
    # 1. adiciona; 2. indexa
    assert run_cli(root, "add", str(src), "--to", "knowledge") == 0
    capsys.readouterr()
    assert run_cli(root, "reindex") == 0
    capsys.readouterr()
    handle_repo = repo_mod.Repo(root)
    # 3. pergunta conhecida responde local com citação
    known = ask(handle_repo, "Configure o resolved com DNS")
    assert known.coverage == "sufficient"
    assert any("doc.md" in cite for cite in known.citations)
    # 4. pergunta desconhecida recusada sem invenção
    unknown = ask(handle_repo, "receita de bolo de cenoura com cobertura")
    assert unknown.coverage == "insufficient"
    assert unknown.citations == []

    # 5+6. pesquisa autorizada gera resposta marcada + rascunho com fontes
    class Web(WebSearch):
        def search(self, query, max_results=5):
            return [Source(url="https://example.org/bolo", title="Bolo",
                           accessed_at="2026-01-01")]

    class Model(RemoteModel):
        def complete(self, prompt):
            return "Misture cenoura com cobertura de chocolate."

    monkeypatch.setattr("lore.research.fetch_page", lambda url: "Bolo de cenoura leva cobertura.")
    result = research(handle_repo, "receita de bolo de cenoura", "",
                      web=Web(), model=Model())
    assert result.ok and "não verificada" in result.answer
    draft = parse_doc(open(result.draft_path, encoding="utf-8").read())
    assert draft.valid and draft.status == "draft"
    assert draft.front["sources"][0]["url"] == "https://example.org/bolo"
    # nenhum rascunho responde como verificado
    assert ask(handle_repo, "receita de bolo de cenoura").citations == []
    # 7. revisa e aprova
    assert any(doc_id == draft.id for doc_id, _, _ in review_mod.queue(handle_repo))
    review_mod.approve(handle_repo, draft.id, human=True)
    # 8. consulta equivalente agora responde localmente
    again = ask(handle_repo, "receita de bolo de cenoura com cobertura")
    assert again.coverage in ("sufficient", "partial")
    assert any(draft.id in cite for cite in again.citations)
    # 9. apaga índice e reindex restaura
    os.remove(index_mod.index_path_for(root))
    assert run_cli(root, "reindex") == 0
    capsys.readouterr()
    assert ask(handle_repo, "Configure o resolved com DNS").coverage == "sufficient"
    # 10. modo offline (só local) responde o que está na base
    offline = ask(handle_repo, "Configure o resolved com DNS", local_only=True)
    assert offline.coverage == "sufficient"
