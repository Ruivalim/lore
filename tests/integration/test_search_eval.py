"""Fase 2: chunking, índice, busca, determinismo, avaliação de recuperação."""

import os
import sqlite3
import time

import pytest

from lore import index as index_mod
from lore import repo as repo_mod
from lore import retrieve as retrieve_mod

# (pergunta, doc_id esperado, trecho do heading esperado ou "")
QUERIES = [
    ("como configurar split DNS no WireGuard", "wireguard-split-dns", "Procedimento"),
    ("resolvectl status wg0", "wireguard-split-dns", "Verificação"),
    ("restic init repositório backup", "restic-x99", "Procedimento"),
    ("restic check integridade", "restic-x99", "Como verificar"),
    ("cafeína antes de dormir", "sono-cafeina", "Evidências"),
    ("evitar café depois das 16h", "sono-cafeina", "Conclusão"),
    ("syncthing send-receive", "syncthing-note", "Notas"),
    ("Tesouro IPCA reserva emergência", "tesouro-ipca", ""),
    ("instalar k3s com script", "k3s-stale", "Comandos"),
    ("chaves públicas por par VPN", "wireguard-geral", ""),
    ("allowed IPs chave pública", "wireguard-geral", "Como funciona"),
    ("DNS por domínio no túnel", "wireguard-split-dns", "Procedimento"),
]


@pytest.fixture()
def indexed_repo(tmp_path):
    import shutil

    root = str(tmp_path / "repo")
    for dirname in ("knowledge", "drafts", "archive"):
        os.makedirs(os.path.join(root, dirname))
    for name in os.listdir("tests/fixtures/corpus"):
        shutil.copy(
            os.path.join("tests/fixtures/corpus", name),
            os.path.join(root, "knowledge", name),
        )
    repo = repo_mod.Repo(root)
    stats = index_mod.build(repo)
    assert stats["docs"] == 7  # draft rascunho-ignorado fica de fora
    return repo


def test_chunking_sections_and_code():
    body = "# T\n\n## A\n\ntexto\n\n```sh\nfoo --bar\n```\n\n## B\n\nmais\n"
    chunks = index_mod.chunk_doc("d", "p", "T", [], "verified", "note", body)
    by_heading = {chunk.heading: chunk for chunk in chunks}
    assert by_heading["A"].body == "texto"
    assert by_heading["A"].code == "foo --bar"
    assert "--bar" not in by_heading["A"].body
    assert by_heading["B"].body == "mais"


def test_diacritics_insensitive(indexed_repo):
    hits = retrieve_mod.search(indexed_repo, "cafeina sono")
    assert hits and hits[0].doc_id == "sono-cafeina"


def test_query_sanitize_rejects_empty():
    with pytest.raises(ValueError):
        retrieve_mod.sanitize_query("   ")


def test_query_special_chars_safe(indexed_repo):
    hits = retrieve_mod.search(indexed_repo, 'restic (init) "repo"')
    assert any(hit.doc_id == "restic-x99" for hit in hits)


def test_draft_never_indexed(indexed_repo):
    hits = retrieve_mod.search(indexed_repo, "DNS mágico resolve tudo")
    assert all(hit.doc_id != "rascunho-ignorado" for hit in hits)


def test_missing_index_errors(tmp_path):
    repo = repo_mod.Repo(str(tmp_path))
    with pytest.raises(retrieve_mod.IndexMissingError):
        retrieve_mod.search(repo, "qualquer coisa")


def test_reindex_deterministic(indexed_repo):
    first = index_mod.build(indexed_repo)
    conn = sqlite3.connect(index_mod.index_path_for(indexed_repo.root))
    dump1 = "\n".join(conn.iterdump())
    conn.close()
    second = index_mod.build(indexed_repo)
    conn = sqlite3.connect(index_mod.index_path_for(indexed_repo.root))
    dump2 = "\n".join(conn.iterdump())
    conn.close()
    assert first == second
    assert dump1 == dump2


def test_reindex_after_delete_restores(indexed_repo):
    os.remove(index_mod.index_path_for(indexed_repo.root))
    with pytest.raises(retrieve_mod.IndexMissingError):
        retrieve_mod.search(indexed_repo, "wireguard")
    stats = index_mod.build(indexed_repo)
    assert stats["docs"] == 7
    assert retrieve_mod.search(indexed_repo, "wireguard")


def test_stale_detection(indexed_repo):
    assert not index_mod.is_stale(indexed_repo)
    path = os.path.join(indexed_repo.root, "knowledge", "restic-x99.md")
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("\nLinha nova.\n")
    assert index_mod.is_stale(indexed_repo)


def test_type_and_tag_filters(indexed_repo):
    hits = retrieve_mod.search(indexed_repo, "wireguard", doc_type="concept")
    assert hits and all(hit.doc_type == "concept" for hit in hits)
    hits = retrieve_mod.search(indexed_repo, "backup", tag="restic")
    assert hits and hits[0].doc_id == "restic-x99"


def test_matched_in_explains(indexed_repo):
    hits = retrieve_mod.search(indexed_repo, "restic-x99")
    assert hits and "title" in hits[0].matched_in


def test_eval_recall_at_3(indexed_repo):
    misses = []
    for query, expected, _heading in QUERIES:
        top3 = [hit.doc_id for hit in retrieve_mod.search(indexed_repo, query, limit=3)]
        if expected not in top3:
            misses.append((query, expected, top3))
    assert not misses, f"recall@3 falhou: {misses}"


def test_eval_section_correct(indexed_repo):
    misses = []
    for query, expected, heading in QUERIES:
        if not heading:
            continue
        hits = retrieve_mod.search(indexed_repo, query, limit=3)
        mine = [hit for hit in hits if hit.doc_id == expected]
        if not mine or heading.lower() not in mine[0].heading.lower():
            misses.append((query, expected, heading,
                           [(h.doc_id, h.heading) for h in hits]))
    assert not misses, f"seção errada: {misses}"


def test_eval_latency(indexed_repo):
    start = time.perf_counter()
    for query, _, _ in QUERIES:
        retrieve_mod.search(indexed_repo, query, limit=5)
    elapsed = (time.perf_counter() - start) / len(QUERIES)
    print(f"\nlatência média por consulta: {elapsed * 1000:.1f}ms")
    assert elapsed < 1.0
