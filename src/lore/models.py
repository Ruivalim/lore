"""Esquema de documentos lore: validação e estados (spec §7, §8)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .front import FrontMatterError, split_front_matter

TYPES = (
    "howto",
    "troubleshooting",
    "reference",
    "concept",
    "decision",
    "research",
    "note",
)

STATUSES = ("draft", "verified", "stale", "archived")

TRANSITIONS: dict[str, tuple[str, ...]] = {
    "draft": ("verified", "archived"),
    "verified": ("stale", "archived"),
    "stale": ("verified", "archived"),
    "archived": (),
}

REQUIRED = (
    "id",
    "title",
    "type",
    "status",
    "tags",
    "created_at",
    "updated_at",
    "sources",
)

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
REVIEW_POLICIES = ("human", "auto-if-clean", "auto")
AUTO_POLICIES = ("auto-if-clean", "auto")
REVIEWERS = ("human", "auto")
SUMMARY_MAX = 600
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class Doc:
    front: dict
    body: str
    path: str = ""
    errors: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return str(self.front.get("id", ""))

    @property
    def status(self) -> str:
        return str(self.front.get("status", ""))

    @property
    def valid(self) -> bool:
        return not self.errors


def _valid_date(value: object) -> bool:
    if not isinstance(value, str) or not DATE_RE.match(value):
        return False
    year, month, day = (int(part) for part in value.split("-"))
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return False
    return True


def validate(front: dict, body: str = "") -> list[str]:
    """Valida front matter. Retorna lista de erros (vazia = válido)."""
    errors: list[str] = []
    if not isinstance(front, dict):
        return ["front matter deve ser um mapa"]

    for key in REQUIRED:
        if key not in front:
            errors.append(f"campo obrigatório ausente: {key}")

    doc_id = front.get("id")
    if doc_id is not None and (
        not isinstance(doc_id, str) or not ID_RE.match(doc_id)
    ):
        errors.append("id deve ser slug minúsculo: [a-z0-9-], sem começar com '-'")

    title = front.get("title")
    if title is not None and (not isinstance(title, str) or not title.strip()):
        errors.append("title deve ser texto não vazio")

    doc_type = front.get("type")
    if doc_type is not None and doc_type not in TYPES:
        errors.append(f"type inválido: {doc_type!r} (esperado um de {', '.join(TYPES)})")

    status = front.get("status")
    if status is not None and status not in STATUSES:
        errors.append(
            f"status inválido: {status!r} (esperado um de {', '.join(STATUSES)})"
        )

    tags = front.get("tags")
    if tags is not None:
        if not isinstance(tags, list) or not tags:
            errors.append("tags deve ser lista não vazia")
        elif any(not isinstance(tag, str) or not tag.strip() for tag in tags):
            errors.append("tags deve conter só texto não vazio")

    reviewed_by = front.get("reviewed_by")
    if reviewed_by is not None and reviewed_by not in REVIEWERS:
        errors.append(f"reviewed_by inválido: {reviewed_by!r} (human ou auto)")

    summary = front.get("summary")
    if summary is not None:
        if not isinstance(summary, str) or not summary.strip():
            errors.append("summary deve ser texto não vazio")
        elif len(summary) > SUMMARY_MAX:
            errors.append(f"summary passa de {SUMMARY_MAX} caracteres")

    for key in ("created_at", "updated_at"):
        value = front.get(key)
        if value is not None and not _valid_date(value):
            errors.append(f"{key} deve ser data YYYY-MM-DD: {value!r}")

    if status == "verified" and not _valid_date(front.get("verified_at")):
        errors.append("verified_at obrigatório (YYYY-MM-DD) quando status é verified")
    for key in ("verified_at", "review_after"):
        value = front.get(key)
        if value is not None and not _valid_date(value):
            errors.append(f"{key} deve ser data YYYY-MM-DD: {value!r}")

    sources = front.get("sources")
    if sources is not None:
        if not isinstance(sources, list):
            errors.append("sources deve ser lista")
        elif not sources:
            # Spec §8.1: vazia somente se experiência ou nota pessoal.
            if doc_type != "note":
                errors.append(
                    "sources vazia só vale para type note ou entrada kind: personal"
                )
        else:
            for entry in sources:
                if not isinstance(entry, dict):
                    errors.append("cada source deve ser um mapa")
                    break
                if entry.get("kind") == "personal":
                    if not entry.get("description"):
                        errors.append("source personal exige description")
                elif entry.get("kind") == "local":
                    if not entry.get("path") or not entry.get("description"):
                        errors.append("source local exige path e description")
                elif not entry.get("url"):
                    errors.append("source externa exige url")
                if entry.get("url") and not isinstance(entry["url"], str):
                    errors.append("source url deve ser texto")

    for key in ("supersedes", "related"):
        value = front.get(key)
        if value is not None and (
            not isinstance(value, list)
            or any(not isinstance(item, str) for item in value)
        ):
            errors.append(f"{key} deve ser lista de ids")

    if body is not None and not body.strip():
        errors.append("corpo Markdown vazio")

    return errors


def parse_doc(text: str, path: str = "") -> Doc:
    """Parseia documento completo. Nunca levanta: erros vão para Doc.errors."""
    try:
        front, body = split_front_matter(text)
    except FrontMatterError as exc:
        return Doc(front={}, body=text, path=path, errors=[str(exc)])
    errors = validate(front, body)
    return Doc(front=front, body=body, path=path, errors=errors)


def can_transition(status: str, new_status: str) -> bool:
    return new_status in TRANSITIONS.get(status, ())


def transition(doc: Doc, new_status: str, human: bool = False,
               policy: str = "") -> list[str]:
    """Aplica transição de estado. Retorna erros (vazio = ok, doc mutado).

    Promoção a verified exige human=True ou uma política de revisão
    automática (`policy`) que o usuário ligou em [review].
    """
    if new_status not in STATUSES:
        return [f"status inválido: {new_status!r}"]
    if not can_transition(doc.status, new_status):
        return [f"transição proibida: {doc.status} -> {new_status}"]
    if new_status == "verified" and not human and policy not in AUTO_POLICIES:
        return ["promoção a verified exige aprovação humana (--human)"]
    doc.front["status"] = new_status
    return []
