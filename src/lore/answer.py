"""Avaliador de cobertura + compositor extrativo (PLAN Fase 3, README §10.5/§10.6).

Regras: responde só com trechos recuperados, cita arquivo e seção, separa
fato de incerteza, declara lacunas, nunca usa draft/archived (nem indexam),
avisa em stale, preserva comandos byte a byte, não esconde conflito.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import urllib.request
from dataclasses import dataclass, field

from . import config as config_mod
from . import index as index_mod
from . import repo as repo_mod
from .retrieve import Hit, LexicalScorer, query_terms

TOP_CHUNKS = 3
RETRIEVE_LIMIT = 10

NEGATION_CUES = (
    "não é", "não deve", "não funciona", "incorreto", "incorreta",
    "errado", "errada", "evite", "cuidado", "desaconselh",
)


@dataclass
class Answer:
    coverage: str  # sufficient | partial | insufficient | conflicting | stale
    text: str
    citations: list[str] = field(default_factory=list)
    gap: list[str] = field(default_factory=list)
    warning: str = ""


def classify(hits: list[Hit], terms: list[str]) -> tuple[str, list[str]]:
    """Classifica cobertura. Auditável: só usa trechos recuperados."""
    if not hits or not terms:
        return "insufficient", list(terms)
    lowered = [term.lower() for term in terms]
    covered: set[str] = set()
    for hit in hits[:5]:
        hay = f"{hit.title} {hit.heading} {hit.snippet}".lower()
        for term in lowered:
            if term in hay:
                covered.add(term)
    uncovered = [term for term in terms if term.lower() not in covered]
    if not covered:
        return "insufficient", uncovered
    if _detect_conflict(hits):
        return "conflicting", uncovered
    if hits[0].status == "stale":
        return "stale", uncovered
    if uncovered:
        return "partial", uncovered
    return "sufficient", []


def _detect_conflict(hits: list[Hit]) -> bool:
    """Conservador: 2+ docs verified, termo compartilhado no corpo, um nega."""
    bodies: dict[str, str] = {}
    for hit in hits[:5]:
        if hit.status != "verified":
            continue
        bodies.setdefault(hit.doc_id, "")
        bodies[hit.doc_id] += f" {hit.title} {hit.heading} {hit.snippet}".lower()
    docs = list(bodies)
    for pos in range(len(docs)):
        for other in range(pos + 1, len(docs)):
            shared = _shared_terms(bodies[docs[pos]], bodies[docs[other]])
            if not shared:
                continue
            first, second = bodies[docs[pos]], bodies[docs[other]]
            if _has_negation(first) != _has_negation(second):
                return True
    return False


def _shared_terms(first: str, second: str) -> set[str]:
    words = lambda text: {word for word in re.findall(r"[\w]+", text) if len(word) >= 4}
    return words(first) & words(second) - {
        "para", "como", "esta", "este", "isso", "entre", "sobre", "quando",
    }


def _has_negation(text: str) -> bool:
    return any(cue in text for cue in NEGATION_CUES)


def cite(hit: Hit) -> str:
    section = f"#{hit.heading}" if hit.heading else ""
    return f"{hit.path}{section}"


def compose_extractive(hits: list[Hit], warning: str = "") -> Answer:
    chosen = hits[:TOP_CHUNKS]
    lines: list[str] = []
    if warning:
        lines.append(f"Aviso: {warning}")
        lines.append("")
    for hit in chosen:
        section = f"#{hit.heading}" if hit.heading else ""
        lines.append(f"Segundo {hit.path}{section}:")
        lines.append("")
        lines.append(hit.snippet.strip() or "(trecho sem texto corrido; ver seção)")
        lines.append("")
    lines.append("Fontes locais:")
    citations = [cite(hit) for hit in chosen]
    for pos, citation in enumerate(citations, 1):
        lines.append(f"  {pos}. {citation}")
    return Answer(coverage="sufficient", text="\n".join(lines).strip() + "\n",
                  citations=citations)


def _full_chunk_text(repo: repo_mod.Repo, hit: Hit) -> str:
    """Texto completo do chunk para síntese (não só o snippet)."""
    conn = sqlite3.connect(index_mod.index_path_for(repo.root))
    try:
        row = conn.execute(
            "SELECT heading, body, code FROM chunks WHERE doc_id = ?"
            " ORDER BY rowid LIMIT 50",
            (hit.doc_id,),
        ).fetchall()
    finally:
        conn.close()
    for heading, body, code in row:
        if (heading or "") == hit.heading:
            parts = [part for part in (body, code) if (part or "").strip()]
            return "\n\n".join(parts)
    return hit.snippet


def synthesize_local(endpoint: str, question: str,
                     context: list[tuple[str, str]], api_key: str = "") -> str:
    """Chama endpoint OpenAI-compatible (stdlib). Levanta em falha."""
    blocks = "\n\n".join(
        f"[fonte: {citation}]\n{text}" for citation, text in context
    )
    prompt = (
        "Responda à pergunta usando SOMENTE os trechos abaixo. "
        "Cite cada afirmação como arquivo#seção entre colchetes. "
        "Não invente comandos nem valores.\n\n"
        f"Pergunta: {question}\n\nTrechos:\n{blocks}\n"
    )
    payload = json.dumps({
        "model": "local",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }).encode()
    request = urllib.request.Request(
        endpoint.rstrip("/") + "/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", **(
            {"Authorization": f"Bearer {api_key}"} if api_key else {})},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        data = json.loads(response.read().decode())
    return data["choices"][0]["message"]["content"]


def validate_synthesis(response: str, citations: list[str]) -> list[str]:
    """Checa citação: sem arquivo inventado, ao menos uma citação real."""
    mentioned = {
        match.group(1)
        for match in re.finditer(r"([\w\-./]+\.md)", response)
    }
    known = {cite.split("#")[0] for cite in citations}
    known_basenames = {os.path.basename(path) for path in known}
    invented = {
        path for path in mentioned
        if os.path.basename(path) not in known_basenames
    }
    errors = [f"arquivo citado não está nas fontes: {path}" for path in sorted(invented)]
    cited = sum(1 for cite in citations if cite in response or cite.split("#")[0] in response)
    if cited == 0:
        errors.append("resposta sem nenhuma citação às fontes")
    return errors


def ask(repo: repo_mod.Repo, question: str, limit: int = TOP_CHUNKS,
        doc_type: str = "", tag: str = "", as_of: str = "",
        local_only: bool = False, extractive: bool = True,
        allow_yes: bool = False) -> Answer:
    """Pipeline ask: recupera, classifica, compõe. Sem rede por padrão."""
    terms = query_terms(question)
    if not terms:
        return Answer(coverage="insufficient", text=(
            "A base não contém uma resposta confiável.\n"
            "(pergunta sem termos pesquisáveis)"
        ), gap=[])
    try:
        hits = LexicalScorer().search(repo, question, RETRIEVE_LIMIT, doc_type, tag)
    except ValueError as exc:
        return Answer(coverage="insufficient", text=(
            f"A base não contém uma resposta confiável.\n({exc})"))
    if as_of:
        hits = [hit for hit in hits if _updated_at(repo, hit.doc_id) <= as_of]
    coverage, gap = classify(hits, terms)
    if coverage == "insufficient":
        return Answer(coverage=coverage, gap=gap, text=(
            "A base não contém uma resposta confiável.\n"
            + ("Pesquisa externa ainda não implementada (Fase 4)."
               if not local_only else "")
        ).strip() + "\n")
    if coverage == "conflicting":
        lines = ["As fontes locais discordam; sem conclusão segura:", ""]
        for hit in hits[:4]:
            lines.append(f"- {cite(hit)}: {hit.snippet.strip()}")
        lines += ["", "Fontes locais:"] + [
            f"  {pos}. {cite(hit)}" for pos, hit in enumerate(hits[:4], 1)]
        return Answer(coverage=coverage, gap=gap,
                      citations=[cite(hit) for hit in hits[:4]],
                      text="\n".join(lines) + "\n")
    if coverage == "partial":
        answer = compose_extractive(hits)
        answer.coverage = "partial"
        answer.gap = gap
        answer.text = (
            f"Encontrei material parcial. Lacuna (sem cobertura): {', '.join(gap)}.\n"
            "A resposta abaixo cobre só o que a base sustenta.\n\n" + answer.text
        )
        return answer
    warning = ""
    if coverage == "stale":
        warning = (f"melhor fonte é stale ({hits[0].path}); "
                   "conteúdo pode estar desatualizado")
    if not extractive:
        cfg, _ = config_mod.load(repo.root)
        endpoint = cfg.get("answer", {}).get("local_model_endpoint", "")
        if endpoint:
            context = [(cite(hit), _full_chunk_text(repo, hit)) for hit in hits[:3]]
            try:
                response = synthesize_local(
                    endpoint, question, context,
                    os.environ.get("LORE_API_KEY", ""))
            except Exception as exc:  # noqa: BLE001 - fallback é o contrato
                warning = f"síntese local falhou ({exc}); usando modo extrativo"
            else:
                citations = [cite(hit) for hit in hits[:3]]
                errors = validate_synthesis(response, citations)
                if not errors:
                    return Answer(coverage=coverage, text=response.strip() + "\n",
                                  citations=citations, warning=warning)
                warning = ("síntese local sem citação válida "
                           f"({'; '.join(errors)}); usando modo extrativo")
        # Sem endpoint: extrativo silencioso (ninguém pediu síntese).
    answer = compose_extractive(hits, warning)
    answer.coverage = coverage
    return answer


def _updated_at(repo: repo_mod.Repo, doc_id: str) -> str:
    conn = sqlite3.connect(index_mod.index_path_for(repo.root))
    try:
        row = conn.execute("SELECT updated_at FROM docs WHERE doc_id = ?",
                           (doc_id,)).fetchone()
    finally:
        conn.close()
    return row[0] if row else ""
