"""Recuperação textual: BM25/FTS5 + boosts por campo (PLAN Fase 2).

Interface Scorer existe para a Fase 6 plugar o scorer semântico ao lado.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

from . import index as index_mod
from . import repo as repo_mod

# Pesos por coluna FTS5: title, tags, heading, body, code.
# Score = soma de peso * termos distintos casados na coluna. Sem norma de
# tamanho: BM25 punia a seção longa que casava mais (bug medido no eval).
COLUMN_WEIGHTS = (4.0, 3.0, 3.0, 1.0, 2.0)

_COLUMN_LABELS = ("title", "tags", "heading", "body", "code")


class IndexMissingError(RuntimeError):
    pass


@dataclass
class Hit:
    doc_id: str
    path: str
    title: str
    status: str
    doc_type: str
    heading: str
    snippet: str
    score: float
    matched_in: list[str] = field(default_factory=list)


class Scorer:
    """Base para scorers. LexicalScorer é o primeiro; semântico entra na Fase 6."""

    name = "base"

    def search(self, repo: repo_mod.Repo, query: str, limit: int = 10,
               doc_type: str = "", tag: str = "") -> list[Hit]:
        raise NotImplementedError


STOPWORDS = frozenset(
    "como para com sem por que dos das nos nas aos ante após "
    "antes depois entre sobre onde quando qual quais meu minha "
    "meus minhas seu sua voce isso isto este esta esse essa "
    "muito mais menos foi sao ser ter tem tive pode fazer "
    "se em de da do no na os as ao e ou a o um uma uns ".split()
)


def sanitize_query(query: str) -> str:
    """Normaliza entrada para MATCH FTS5: termos citados com OR.

    OR + BM25 ranqueia por cobertura em vez de exigir tudo (AND
    recusava pergunta real por causa de stopword ou flexão)."""
    tokens = re.findall(r"[\w]+", query, flags=re.UNICODE)
    kept = [
        tok for tok in tokens
        if len(tok) >= 3 and tok.lower() not in STOPWORDS
    ]
    if not kept:
        raise ValueError("consulta vazia")
    return " OR ".join(f'"{tok}"' for tok in kept)


def _column_hits(conn: sqlite3.Connection, match: str, rowid: int) -> list[int]:
    """Conta casamentos por coluna via highlight (offsets() indisponível aqui)."""
    cols = ", ".join(
        f"highlight(chunks, {pos}, '<b>', '</b>')" for pos in range(1, 6)
    )
    try:
        row = conn.execute(
            f"SELECT {cols} FROM chunks WHERE rowid = ? AND chunks MATCH ?",
            (rowid, match),
        ).fetchone()
    except sqlite3.Error:
        return [0, 0, 0, 0, 0]
    if row is None:
        return [0, 0, 0, 0, 0]
    return [str(cell or "").count("<b>") for cell in row]


def _score_counts(counts: list[int]) -> tuple[float, int]:
    import math

    score = 0.0
    for pos, total in enumerate(counts):
        if total > 0:
            score += COLUMN_WEIGHTS[pos] * (1.0 + math.log(total))
    return score, sum(counts)



class LexicalScorer(Scorer):
    name = "lexical"

    def search(self, repo: repo_mod.Repo, query: str, limit: int = 10,
               doc_type: str = "", tag: str = "") -> list[Hit]:
        path = index_mod.index_path_for(repo.root)
        import os

        if not os.path.isfile(path):
            raise IndexMissingError("índice não existe; rode: lore reindex")
        match = sanitize_query(query)
        conn = sqlite3.connect(path)
        try:
            sql = "SELECT rowid, doc_id FROM chunks WHERE chunks MATCH ?"
            params: list = [match]
            try:
                rows = conn.execute(sql, params).fetchall()
            except sqlite3.Error as exc:
                raise ValueError(f"consulta inválida para o índice: {exc}") from exc
            hits: list[Hit] = []
            for rowid, doc_id in rows:
                counts = _column_hits(conn, match, rowid)
                score, total_hits = _score_counts(counts)
                meta = conn.execute(
                    "SELECT path, status, doc_type, title, tags FROM docs WHERE doc_id = ?",
                    (doc_id,),
                ).fetchone()
                if meta is None:
                    continue
                doc_path, status, dtype, title, _tags = meta
                if doc_type and dtype != doc_type:
                    continue
                if tag and not _tag_match(conn, doc_id, tag):
                    continue
                matched = [
                    label for label, total in zip(_COLUMN_LABELS, counts) if total > 0
                ]
                heading, body_text, code_text = conn.execute(
                    "SELECT heading, body, code FROM chunks WHERE rowid = ?",
                    (rowid,),
                ).fetchone()
                if (
                    not (body_text or "").strip()
                    and not (code_text or "").strip()
                    and (heading or "") == title
                ):
                    continue  # H1 sem corpo só herdou boost do título
                snip = conn.execute(
                    "SELECT snippet(chunks, 4, '[', ']', '...', 24)"
                    " FROM chunks WHERE rowid = ? AND chunks MATCH ?",
                    (rowid, match),
                ).fetchone()[0]
                hits.append(Hit(doc_id=doc_id, path=doc_path, title=title,
                                status=status, doc_type=dtype, heading=heading or "",
                                snippet=snip or "", score=score + total_hits * 0.01,
                                matched_in=matched))
            hits.sort(key=lambda hit: hit.score, reverse=True)
            return hits[:limit]
        finally:
            conn.close()


def _tag_match(conn: sqlite3.Connection, doc_id: str, tag: str) -> bool:
    (tags,) = conn.execute("SELECT tags FROM docs WHERE doc_id = ?",
                           (doc_id,)).fetchone()
    return tag.lower() in tags.split(" ")


def search(repo: repo_mod.Repo, query: str, limit: int = 10,
           doc_type: str = "", tag: str = "") -> list[Hit]:
    return LexicalScorer().search(repo, query, limit, doc_type, tag)
