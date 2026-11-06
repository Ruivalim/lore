"""Busca semântica opcional (plano, Fase 6). Desligada por padrão.

Backends de embedding (interface Embedder):
- HashEmbedder: trigramas de chars com hashing, stdlib, determinístico.
  Fraco, mas mede se fusão ajuda sem baixar nada.
- EndpointEmbedder: endpoint OpenAI-compatible (/embeddings), modelo local
  real (llama.cpp, ollama, etc). Chave via LORE_API_KEY, nunca em arquivo.

Vetores ficam em tabela SQLite separada, descartável junto com reindex.
Kill switch: retrieval.semantic=false volta ao textual puro (Fase 2).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import struct
import urllib.request
from dataclasses import dataclass

from . import index as index_mod
from . import repo as repo_mod

DIM = 256
VECTORS_TABLE = "vectors"


class Embedder:
    name = "base"
    dim = DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class HashEmbedder(Embedder):
    """Trigramas hashados, L2-normalizados. Determinístico, sem rede."""

    name = "hash"

    def __init__(self, dim: int = DIM):
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(text) for text in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        padded = "  " + text.lower() + "  "
        for pos in range(len(padded) - 2):
            trigram = padded[pos: pos + 3]
            if trigram.strip():
                slot = int(hashlib.md5(trigram.encode()).hexdigest(), 16) % self.dim
                vec[slot] += 1.0
        norm = math.sqrt(sum(value * value for value in vec)) or 1.0
        return [value / norm for value in vec]


class EndpointEmbedder(Embedder):
    name = "endpoint"

    def __init__(self, endpoint: str, model: str, api_key: str = ""):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.dim = 0  # descoberto no primeiro embed

    def embed(self, texts: list[str]) -> list[list[float]]:
        payload = json.dumps({"model": self.model, "input": texts}).encode()
        request = urllib.request.Request(
            self.endpoint + "/embeddings", data=payload,
            headers={"Content-Type": "application/json", **(
                {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {})},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.loads(response.read().decode())
        vectors = [item["embedding"] for item in data["data"]]
        if vectors and self.dim == 0:
            self.dim = len(vectors[0])
        return vectors


def cosine(first: list[float], second: list[float]) -> float:
    return sum(a * b for a, b in zip(first, second))


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"<{len(vec)}f", *vec)


def _unpack(blob: bytes) -> list[float]:
    count = len(blob) // 4
    return list(struct.unpack(f"<{count}f", blob))


@dataclass
class SemanticHit:
    doc_id: str
    heading: str
    score: float


def build_vectors(repo: repo_mod.Repo, embedder: Embedder) -> dict:
    """(Re)cria tabela de vetores a partir dos chunks indexados."""
    from .index import chunk_doc

    db = index_mod.index_path_for(repo.root)
    if not os.path.isfile(db):
        raise RuntimeError("índice não existe; rode reindex textual primeiro")
    conn = sqlite3.connect(db)
    try:
        conn.execute("DROP TABLE IF EXISTS vectors")
        conn.execute(
            "CREATE TABLE vectors (doc_id TEXT, position INT, vec BLOB,"
            " PRIMARY KEY (doc_id, position))")
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES "
                     "('embedder', ?)", (embedder.name,))
        docs = conn.execute(
            "SELECT doc_id, path, title, tags FROM docs").fetchall()
        texts: list[str] = []
        keys: list[tuple[str, int]] = []
        for doc_id, path, title, tags in docs:
            with open(path, encoding="utf-8") as handle:
                from .models import parse_doc
                doc = parse_doc(handle.read(), path)
            chunks = chunk_doc(doc_id, path, title, tags.split(" "),
                               "", "", doc.body)
            for chunk in chunks:
                texts.append(f"{chunk.title}\n{chunk.heading}\n{chunk.body}")
                keys.append((doc_id, chunk.position))
        count = 0
        for pos in range(0, len(texts), 32):
            batch = texts[pos: pos + 32]
            for key, vec in zip(keys[pos: pos + 32], embedder.embed(batch)):
                conn.execute("INSERT INTO vectors (doc_id, position, vec)"
                             " VALUES (?, ?, ?)", (key[0], key[1], _pack(vec)))
                count += 1
        conn.commit()
        return {"vectors": count, "embedder": embedder.name}
    finally:
        conn.close()


def has_vectors(repo: repo_mod.Repo) -> bool:
    db = index_mod.index_path_for(repo.root)
    if not os.path.isfile(db):
        return False
    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE name='vectors'").fetchone()
        return row is not None
    finally:
        conn.close()


def semantic_search(repo: repo_mod.Repo, query: str, embedder: Embedder,
                    limit: int = 20) -> list[SemanticHit]:
    db = index_mod.index_path_for(repo.root)
    if not has_vectors(repo):
        raise RuntimeError("vetores ausentes; rode: lore reindex --semantic")
    query_vec = embedder.embed([query])[0]
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT doc_id, position, vec FROM vectors").fetchall()
        headings: dict[tuple[str, int], str] = {}
        for (doc_id,) in conn.execute("SELECT doc_id FROM docs"):
            ordered = conn.execute(
                "SELECT heading FROM chunks WHERE doc_id = ? ORDER BY rowid",
                (doc_id,)).fetchall()
            for pos, (heading,) in enumerate(ordered):
                headings[(doc_id, pos)] = heading or ""
    finally:
        conn.close()
    # Posição do chunk no índice vetorial vs rowid do FTS podem divergir;
    # usa (doc_id, position) com fallback para heading vazio.
    scored = []
    for doc_id, position, blob in rows:
        vec = _unpack(blob)
        if len(vec) != len(query_vec):
            continue
        scored.append((cosine(query_vec, vec), doc_id, position))
    scored.sort(reverse=True)
    return [SemanticHit(doc_id=doc_id, heading=headings.get((doc_id, pos), ""),
                        score=score)
            for score, doc_id, pos in scored[:limit]]
