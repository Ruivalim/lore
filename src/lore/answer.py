"""Avaliador de cobertura + compositor extrativo (plano, Fase 3, spec §10.5/§10.6).

Regras: responde só com trechos recuperados, cita arquivo e seção, separa
fato de incerteza, declara lacunas, nunca usa draft/archived (nem indexam),
avisa em stale, preserva comandos byte a byte, não esconde conflito.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass, field

from . import config as config_mod
from . import index as index_mod
from . import repo as repo_mod
from .retrieve import Hit, IndexMissingError, LexicalScorer, query_terms

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
    context: list[tuple[str, str]] = field(default_factory=list)
    # Resposta direta de 1 a 3 frases, com citação. Vazia: só há a completa.
    short: str = ""


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
        # Evidência só-semântica: relevante, mas sem verificação termo a termo.
        if any("semantic" in hit.matched_in for hit in hits[:3]):
            return "partial", uncovered
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
    def words(text: str) -> set[str]:
        return {word for word in re.findall(r"[\w]+", text) if len(word) >= 4}

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


def synthesis_prompt(question: str, context: list[tuple[str, str]]) -> str:
    blocks = "\n\n".join(
        f"[fonte: {citation}]\n{text}" for citation, text in context
    )
    return (
        "Responda à pergunta usando SOMENTE os trechos abaixo. "
        "Cite cada afirmação como arquivo#seção entre colchetes. "
        "Não invente comandos nem valores. Responda no idioma da pergunta.\n\n"
        "Devolva só um objeto JSON, sem bloco Markdown, com duas chaves:\n"
        '- "short": a resposta direta, de 1 a 3 frases, com ao menos uma citação;\n'
        '- "long": a resposta completa, com contexto, passos e citações.\n\n'
        f"Pergunta: {question}\n\nTrechos:\n{blocks}\n"
    )


def parse_short_long(response: str) -> tuple[str, str]:
    """(curta, longa) de uma resposta JSON. Sem JSON utilizável, tudo é longa.

    Agente pode embrulhar o JSON em bloco Markdown ou texto antes e depois:
    vale o primeiro objeto com "long" texto. Nunca levanta.
    """
    text = response.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict) and isinstance(data.get("long"), str) \
                and data["long"].strip():
            short = data.get("short")
            return (short.strip() if isinstance(short, str) else ""), data["long"].strip()
    return "", response.strip()


def synthesize(agent, question: str, context: list[tuple[str, str]]) -> str:
    """Síntese pelo agente da tarefa answer. Levanta em falha."""
    return agent.complete(synthesis_prompt(question, context))


def summary_of(repo: repo_mod.Repo, doc_id: str) -> str:
    """`summary` do front matter, ou ''. Lido do arquivo, não do índice."""
    doc = repo_mod.find_by_id(repo, doc_id)
    if doc is None:
        return ""
    summary = doc.front.get("summary")
    return summary.strip() if isinstance(summary, str) else ""


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
    # Citar só o nome do arquivo vale: a checagem de inventado já é por nome.
    cited = len({os.path.basename(path) for path in mentioned} & known_basenames)
    if cited == 0:
        errors.append("resposta sem nenhuma citação às fontes")
    return errors


def ask(repo: repo_mod.Repo, question: str, limit: int = TOP_CHUNKS,
        doc_type: str = "", tag: str = "", as_of: str = "",
        local_only: bool = False, extractive: bool = True,
        allow_yes: bool = False, semantic: bool = False, embedder=None,
        lex_weight: float = 0.7, sem_weight: float = 0.3) -> Answer:
    """Pipeline ask: recupera, classifica, compõe. Sem rede por padrão."""
    terms = query_terms(question)
    if not terms:
        return Answer(coverage="insufficient", text=(
            "A base não contém uma resposta confiável.\n"
            "(pergunta sem termos pesquisáveis)"
        ), gap=[])
    sem_warning = ""
    try:
        if semantic:
            from .retrieve import search_hybrid

            try:
                hits = search_hybrid(repo, question, embedder,
                                     RETRIEVE_LIMIT, doc_type, tag,
                                     lex_weight, sem_weight)
            except RuntimeError as exc:
                sem_warning = f"{exc}; usando busca textual"
                hits = LexicalScorer().search(repo, question, RETRIEVE_LIMIT,
                                              doc_type, tag)
        else:
            hits = LexicalScorer().search(repo, question, RETRIEVE_LIMIT,
                                          doc_type, tag)
    except (ValueError, IndexMissingError) as exc:
        return Answer(coverage="insufficient", text=(
            f"A base não contém uma resposta confiável.\n({exc})"))
    if as_of:
        hits = [hit for hit in hits if _updated_at(repo, hit.doc_id) <= as_of]
    coverage, gap = classify(hits, terms)
    if coverage == "insufficient":
        return Answer(coverage=coverage, gap=gap, text=(
            "A base não contém uma resposta confiável.\n"
        ))
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
        answer.context = [
            (cite(hit), _full_chunk_text(repo, hit)) for hit in hits[:TOP_CHUNKS]
        ]
        answer.text = (
            f"Encontrei material parcial. Lacuna (sem cobertura): {', '.join(gap)}.\n"
            "A resposta abaixo cobre só o que a base sustenta.\n"
            + (f"Aviso: {sem_warning}\n" if sem_warning else "")
            + "\n" + answer.text
        )
        return answer
    warning = ""
    if sem_warning:
        warning = sem_warning
    if coverage == "stale":
        stale_note = (f"melhor fonte é stale ({hits[0].path}); "
                       "conteúdo pode estar desatualizado")
        warning = f"{warning}; {stale_note}" if warning else stale_note
    if not extractive:
        from . import agents as agents_mod

        cfg, _ = config_mod.load(repo.root)
        try:
            agent = agents_mod.resolve(cfg, "answer")
        except ValueError as exc:
            agent = None
            warning = f"{warning}; {exc}" if warning else str(exc)
        if agent is not None:
            context = [(cite(hit), _full_chunk_text(repo, hit)) for hit in hits[:3]]
            try:
                response = synthesize(agent, question, context)
            except Exception as exc:  # noqa: BLE001 - fallback é o contrato
                warning = f"síntese com {agent.name} falhou ({exc}); usando modo extrativo"
            else:
                citations = [cite(hit) for hit in hits[:3]]
                short, long = parse_short_long(response)
                errors = validate_synthesis(long, citations)
                if not errors:
                    # Curta sem citação válida some: a longa continua de pé.
                    if short and validate_synthesis(short, citations):
                        short = ""
                    return Answer(coverage=coverage, text=long + "\n",
                                  citations=citations, warning=warning, short=short)
                warning = (f"síntese com {agent.name} sem citação válida "
                           f"({'; '.join(errors)}); usando modo extrativo")
    answer = compose_extractive(hits, warning)
    answer.coverage = coverage
    top = hits[0]
    summary = summary_of(repo, top.doc_id) if top.status == "verified" else ""
    if summary:
        answer.short = f"{summary} [{cite(top)}]"
    return answer


def _updated_at(repo: repo_mod.Repo, doc_id: str) -> str:
    conn = sqlite3.connect(index_mod.index_path_for(repo.root))
    try:
        row = conn.execute("SELECT updated_at FROM docs WHERE doc_id = ?",
                           (doc_id,)).fetchone()
    finally:
        conn.close()
    return row[0] if row else ""
