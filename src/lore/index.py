"""Indexador local: Markdown -> chunks por seção -> SQLite FTS5 (PLAN Fase 2).

Descartável e reconstruível. Só entram docs verified/stale como fonte
confiável; draft/archived nunca respondem, então nem indexam.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from dataclasses import dataclass

from . import repo as repo_mod

INDEX_NAME = "index.sqlite"
SCHEMA_VERSION = 1

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE_RE = re.compile(r"^(`{3,}|~{3,})")


@dataclass
class Chunk:
    doc_id: str
    path: str
    title: str
    tags: list[str]
    status: str
    doc_type: str
    heading: str
    level: int
    body: str
    code: str
    position: int


def index_path_for(root: str) -> str:
    return os.path.join(root, ".lore", INDEX_NAME)


def split_sections(body: str) -> list[tuple[str, int, list[str]]]:
    """Divide corpo em (heading, nível, linhas). Pré-cabeçalho vira seção ''."""
    sections: list[tuple[str, int, list[str]]] = []
    heading, level, buf = "", 0, []
    in_fence = False
    for line in body.splitlines():
        fence = FENCE_RE.match(line.strip())
        if fence:
            in_fence = not in_fence
            buf.append(line)
            continue
        match = HEADING_RE.match(line) if not in_fence else None
        if match:
            sections.append((heading, level, buf))
            heading = match.group(2)
            level = len(match.group(1))
            buf = []
        else:
            buf.append(line)
    sections.append((heading, level, buf))
    return sections


def extract_code(lines: list[str]) -> str:
    """Extrai conteúdo de blocos cercados, fora do texto corrido."""
    out: list[str] = []
    in_fence = False
    for line in lines:
        if FENCE_RE.match(line.strip()):
            in_fence = not in_fence
            continue
        if in_fence:
            out.append(line)
    return "\n".join(out).strip()


def strip_code(lines: list[str]) -> str:
    kept: list[str] = []
    in_fence = False
    for line in lines:
        if FENCE_RE.match(line.strip()):
            in_fence = not in_fence
            continue
        if not in_fence:
            kept.append(line)
    return "\n".join(kept).strip()


def chunk_doc(doc_id: str, path: str, title: str, tags: list[str],
              status: str, doc_type: str, body: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    for position, (heading, level, lines) in enumerate(split_sections(body)):
        text = strip_code(lines)
        code = extract_code(lines)
        if not text and not code and heading == "":
            continue
        chunks.append(
            Chunk(
                doc_id=doc_id, path=path, title=title, tags=tags,
                status=status, doc_type=doc_type, heading=heading,
                level=level, body=text, code=code, position=position,
            )
        )
    return chunks


def _connect(path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _create(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE docs (
            doc_id TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            status TEXT NOT NULL,
            doc_type TEXT NOT NULL,
            title TEXT NOT NULL,
            tags TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT '',
            hash TEXT NOT NULL
        );
        CREATE VIRTUAL TABLE chunks USING fts5(
            doc_id UNINDEXED,
            title,
            tags,
            heading,
            body,
            code,
            tokenize = 'unicode61 remove_diacritics 1'
        );
        """
    )
    conn.execute("INSERT INTO meta (key, value) VALUES ('schema', ?)",
                 (str(SCHEMA_VERSION),))


def file_hash(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def build(repo: repo_mod.Repo) -> dict:
    """Reconstrói índice do zero, ordem determinística por doc_id."""
    path = index_path_for(repo.root)
    if os.path.exists(path):
        os.remove(path)
    conn = _connect(path)
    try:
        _create(conn)
        n_docs = 0
        n_chunks = 0
        docs = sorted(
            (doc for doc in repo_mod.load_all(repo) if doc.valid),
            key=lambda doc: doc.id.lower(),
        )
        for doc in docs:
            # Draft/archived não indexam: nunca respondem como confiável.
            if doc.status not in ("verified", "stale"):
                continue
            front = doc.front
            title = str(front.get("title", ""))
            tags = [str(tag) for tag in front.get("tags", [])]
            chunks = chunk_doc(
                doc.id, doc.path, title, tags,
                doc.status, str(front.get("type", "")), doc.body,
            )
            conn.execute(
                "INSERT INTO docs (doc_id, path, status, doc_type, title, tags,"
                " updated_at, hash)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (doc.id, doc.path, doc.status, str(front.get("type", "")),
                 title, " ".join(tag.lower() for tag in tags),
                 str(front.get("updated_at", "")),
                 file_hash(doc.path)),
            )
            for chunk in chunks:
                conn.execute(
                    "INSERT INTO chunks (doc_id, title, tags, heading, body, code)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (chunk.doc_id, chunk.title, " ".join(chunk.tags),
                     chunk.heading, chunk.body, chunk.code),
                )
                n_chunks += 1
            n_docs += 1
        conn.commit()
        return {"docs": n_docs, "chunks": n_chunks, "path": path}
    finally:
        conn.close()


def is_stale(repo: repo_mod.Repo) -> bool:
    """True se índice ausente ou dessincronizado dos Markdown."""
    path = index_path_for(repo.root)
    if not os.path.isfile(path):
        return True
    try:
        conn = sqlite3.connect(path)
    except sqlite3.Error:
        return True
    try:
        rows = dict(conn.execute("SELECT doc_id, hash FROM docs").fetchall())
    except sqlite3.Error:
        return True
    finally:
        conn.close()
    current: dict[str, str] = {}
    for doc in repo_mod.load_all(repo):
        if doc.valid and doc.status in ("verified", "stale"):
            current[doc.id] = file_hash(doc.path)
    return rows != current
