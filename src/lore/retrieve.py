"""Recuperação textual: BM25/FTS5 + boosts por campo (plano, Fase 2).

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
    "se em de da do no na os as ao e ou a o um uma uns "
    # inglês: pergunta pode vir em outra língua que a da base
    "how what which who whom why when where does did the and for with "
    "from that this these those can could should would are was were has "
    "have had you your into about any some get ".split()
)


def query_terms(query: str) -> list[str]:
    """Termos significativos da pergunta (sem stopwords, len>=3)."""
    tokens = re.findall(r"[\w]+", query, flags=re.UNICODE)
    return [tok for tok in tokens if len(tok) >= 3 and tok.lower() not in STOPWORDS]


def sanitize_query(query: str) -> str:
    """Normaliza entrada para MATCH FTS5: termos citados com OR.

    OR + BM25 ranqueia por cobertura em vez de exigir tudo (AND
    recusava pergunta real por causa de stopword ou flexão)."""
    kept = query_terms(query)
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


def search_hybrid(repo: repo_mod.Repo, query: str, embedder,
                  limit: int = 10, doc_type: str = "", tag: str = "",
                  lex_weight: float = 0.7, sem_weight: float = 0.3,
                  sem_floor: float = 0.45) -> list[Hit]:
    """Fusão textual + semântica com pesos calibrados (docs/CALIBRATION.md).

    Achado só-semântico entra só acima de sem_floor: sem isso, query
    lixo ganhava resposta de ruído."""
    from .semantic import semantic_search

    lexical = LexicalScorer().search(repo, query, 20, doc_type, tag)
    semantic = semantic_search(repo, query, embedder, 20)
    top = max([hit.score for hit in lexical], default=0.0)
    bottom = min([hit.score for hit in lexical], default=0.0)
    span = (top - bottom) or 1.0
    combined: dict[tuple[str, str], list] = {}
    for hit in lexical:
        combined[(hit.doc_id, hit.heading)] = [
            hit, lex_weight * (hit.score - bottom) / span, 0.0]
    for sem in semantic:
        key = (sem.doc_id, sem.heading)
        if key in combined:
            combined[key][2] = sem_weight * max(0.0, sem.score)
        elif sem.score >= sem_floor:
            hit = _hit_from_semantic(repo, sem, doc_type, tag)
            if hit is not None:
                combined[key] = [hit, 0.0, sem_weight * max(0.0, sem.score)]
    ranked = sorted(combined.values(),
                    key=lambda entry: entry[1] + entry[2], reverse=True)
    hits = []
    for hit, lex_score, sem_score in ranked[:limit]:
        hit.score = lex_score + sem_score
        if "semantic" not in hit.matched_in and sem_score > 0:
            hit.matched_in = hit.matched_in + ["semantic"]
        hits.append(hit)
    return hits


def _hit_from_semantic(repo: repo_mod.Repo, sem, doc_type: str, tag: str):
    """Constrói Hit para achado só-semântico (sem par lexical)."""
    import os
    import sqlite3

    from . import index as index_mod

    conn = sqlite3.connect(index_mod.index_path_for(repo.root))
    try:
        meta = conn.execute(
            "SELECT path, status, doc_type, title FROM docs WHERE doc_id = ?",
            (sem.doc_id,)).fetchone()
        if meta is None:
            return None
        doc_path, status, dtype, title = meta
        if doc_type and dtype != doc_type:
            return None
        row = conn.execute(
            "SELECT body FROM chunks WHERE doc_id = ? AND heading = ?"
            " ORDER BY rowid LIMIT 1", (sem.doc_id, sem.heading)).fetchone()
        if row is None:
            return None
    finally:
        conn.close()
    if not os.path.isfile(doc_path):
        return None
    snippet = (row[0] or "")[:300]
    return Hit(doc_id=sem.doc_id, path=doc_path, title=title, status=status,
                doc_type=dtype, heading=sem.heading, snippet=snippet,
                score=0.0, matched_in=["semantic"])
