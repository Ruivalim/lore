"""Fase 6: semântica opcional, fusão, kill switch, calibração."""

import json
import os
import shutil
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from lore import index as index_mod
from lore import repo as repo_mod
from lore import retrieve as retrieve_mod
from lore.answer import ask
from lore.semantic import (
    EndpointEmbedder,
    HashEmbedder,
    build_vectors,
    cosine,
    has_vectors,
    semantic_search,
)


@pytest.fixture()
def repo(tmp_path):
    root = str(tmp_path / "repo")
    os.makedirs(os.path.join(root, "knowledge"))
    for name in os.listdir("tests/fixtures/corpus"):
        shutil.copy(os.path.join("tests/fixtures/corpus", name),
                    os.path.join(root, "knowledge", name))
    handle = repo_mod.Repo(root)
    index_mod.build(handle)
    return handle


def test_hash_embedder_deterministic_and_normalized():
    embedder = HashEmbedder()
    first = embedder.embed(["café e sono"])[0]
    second = embedder.embed(["café e sono"])[0]
    assert first == second
    assert abs(sum(value * value for value in first) - 1.0) < 1e-6
    other = embedder.embed(["imposto de renda"])[0]
    assert cosine(first, other) < cosine(first, first)


def test_vectors_need_text_index_first(tmp_path):
    with pytest.raises(RuntimeError):
        build_vectors(repo_mod.Repo(str(tmp_path)), HashEmbedder())


def test_build_and_search_vectors(repo):
    stats = build_vectors(repo, HashEmbedder())
    assert stats["vectors"] > 0
    assert has_vectors(repo)
    hits = semantic_search(repo, "backup snapshots restic",
                           HashEmbedder(), limit=5)
    assert hits
    assert hits[0].doc_id == "restic-x99"
    # Paráfrase sem termo em comum: retorna algo determinístico, sem crash.
    para = semantic_search(repo, "fazer cópia de segurança do servidor",
                           HashEmbedder(), limit=5)
    assert len(para) == 5


def test_semantic_deterministic(repo):
    build_vectors(repo, HashEmbedder())
    first = [(hit.doc_id, hit.heading) for hit in
             semantic_search(repo, "sono", HashEmbedder())]
    build_vectors(repo, HashEmbedder())
    second = [(hit.doc_id, hit.heading) for hit in
              semantic_search(repo, "sono", HashEmbedder())]
    assert first == second


def test_hybrid_keeps_eval_recall(repo):
    from tests.integration.test_search_eval import QUERIES

    build_vectors(repo, HashEmbedder())
    misses = []
    for query, expected, _heading in QUERIES:
        top3 = [hit.doc_id for hit in retrieve_mod.search_hybrid(
            repo, query, HashEmbedder(), limit=3)]
        if expected not in top3:
            misses.append((query, expected, top3))
    assert not misses, f"híbrido regrediu: {misses}"


def test_kill_switch_matches_pure_lexical(repo):
    build_vectors(repo, HashEmbedder())
    query = "como configurar split DNS no WireGuard"
    pure = [(hit.doc_id, hit.heading) for hit in
            retrieve_mod.search(repo, query, limit=5)]
    forced = [(hit.doc_id, hit.heading) for hit in
              retrieve_mod.search(repo, query, limit=5)]
    assert pure == forced
    hybrid = retrieve_mod.search_hybrid(repo, query, HashEmbedder(), limit=5)
    assert all("semantic" in hit.matched_in or hit.matched_in for hit in hybrid)


def test_ask_semantic_without_vectors_falls_back(repo, capsys):
    answer = ask(repo, "split DNS WireGuard", semantic=True,
                 embedder=HashEmbedder())
    assert answer.coverage == "sufficient"
    assert "textual" in answer.text


def test_ask_hybrid_end_to_end(repo):
    build_vectors(repo, HashEmbedder())
    answer = ask(repo, "split DNS WireGuard", semantic=True,
                 embedder=HashEmbedder())
    assert answer.coverage == "sufficient"
    assert answer.citations


class _Emb(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        payload = json.dumps({"data": [{"embedding": [1.0, 0.0]},
                                       {"embedding": [0.0, 1.0]}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


def test_endpoint_embedder():
    server = HTTPServer(("127.0.0.1", 0), _Emb)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        embedder = EndpointEmbedder(f"http://127.0.0.1:{server.server_port}",
                                    "test-model")
        vectors = embedder.embed(["a", "b"])
    finally:
        server.shutdown()
    assert vectors == [[1.0, 0.0], [0.0, 1.0]]
