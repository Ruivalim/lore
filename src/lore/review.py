"""Fila de revisão e promoção de rascunhos (PLAN Fase 5, README §6.4).

Nenhuma promoção a verified sem human=True. Modelos chamam as mesmas
funções e recebem erro.
"""

from __future__ import annotations

import datetime
import difflib
import os
import subprocess

from . import index as index_mod
from . import repo as repo_mod
from .models import parse_doc, transition


def _today() -> str:
    return datetime.date.today().isoformat()


def queue(repo: repo_mod.Repo) -> list[tuple[str, str, str]]:
    """Fila: (id, path, motivo), ordenada por updated_at."""
    items: list[tuple[str, str, str, str]] = []
    for doc in repo_mod.load_all(repo):
        if not doc.valid:
            continue
        status = doc.status
        updated = str(doc.front.get("updated_at", ""))
        if status == "draft":
            items.append((updated, doc.id, doc.path, "aguarda revisão"))
        elif status == "stale":
            items.append((updated, doc.id, doc.path, "revisar atualidade"))
        elif status == "verified":
            review_after = doc.front.get("review_after")
            if isinstance(review_after, str) and review_after < _today():
                items.append((updated, doc.id, doc.path,
                              f"vencido (review_after {review_after})"))
    items.sort()
    return [(doc_id, path, reason) for _, doc_id, path, reason in items]


def unsourced_claims(body: str, limit: int = 10) -> list[str]:
    """Linhas afirmativas longas sem marcador de fonte. Heurística, não prova."""
    claims = []
    in_fence = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not stripped or stripped.startswith("#"):
            continue
        if len(stripped) < 60:
            continue
        if any(marker in stripped for marker in ("[", "http", "Segundo", "fonte:")):
            continue
        claims.append(stripped[:160])
        if len(claims) >= limit:
            break
    return claims


def possible_conflicts(repo: repo_mod.Repo, doc_id: str) -> list[str]:
    """Docs verified/stale com 2+ tags em comum. Candidatos, não veredito."""
    target = repo_mod.find_by_id(repo, doc_id)
    if target is None:
        return []
    tags = {str(tag).lower() for tag in target.front.get("tags", [])}
    found = []
    for doc in repo_mod.load_all(repo):
        if doc.id.lower() == doc_id.lower() or doc.status not in ("verified", "stale"):
            continue
        shared = tags & {str(tag).lower() for tag in doc.front.get("tags", [])}
        if len(shared) >= 2:
            found.append(f"{doc.id} (tags em comum: {', '.join(sorted(shared))})")
    return found


def diff_against(repo: repo_mod.Repo, doc_id: str) -> str:
    """Diff contra doc em supersedes, se existir."""
    doc = repo_mod.find_by_id(repo, doc_id)
    if doc is None:
        return ""
    supersedes = doc.front.get("supersedes") or []
    if not supersedes:
        return ""
    previous = repo_mod.find_by_id(repo, str(supersedes[0]))
    if previous is None:
        return f"supersedes aponta para id inexistente: {supersedes[0]}"
    diff = difflib.unified_diff(
        previous.body.splitlines(), doc.body.splitlines(),
        fromfile=previous.id, tofile=doc.id, lineterm="")
    return "\n".join(diff)


def detail(repo: repo_mod.Repo, doc_id: str) -> dict:
    doc = repo_mod.find_by_id(repo, doc_id)
    if doc is None:
        raise KeyError(f"id não encontrado: {doc_id}")
    return {
        "id": doc.id,
        "path": doc.path,
        "front": doc.front,
        "body": doc.body,
        "valid": doc.valid,
        "errors": doc.errors,
        "unsourced_claims": unsourced_claims(doc.body),
        "possible_conflicts": possible_conflicts(repo, doc_id),
        "diff": diff_against(repo, doc_id),
    }


def _move(doc_path: str, dest_dir: str) -> str:
    dest = os.path.join(dest_dir, os.path.basename(doc_path))
    if os.path.exists(dest):
        raise ValueError(f"destino já existe: {dest}")
    os.rename(doc_path, dest)
    return dest


def _rewrite(doc, repo: repo_mod.Repo) -> None:
    repo_mod.save_atomic(
        doc.path, repo_mod.render_doc(doc.front, doc.body))


def approve(repo: repo_mod.Repo, doc_id: str, human: bool = False) -> str:
    """Promove draft a verified e reindexa. Exige human=True."""
    doc = repo_mod.find_by_id(repo, doc_id)
    if doc is None:
        raise KeyError(f"id não encontrado: {doc_id}")
    if not doc.valid:
        raise ValueError(f"documento inválido: {'; '.join(doc.errors)}")
    if doc.status != "draft":
        raise ValueError(f"só draft pode ser aprovado (atual: {doc.status})")
    errors = transition(doc, "verified", human=human)
    if errors:
        raise ValueError("; ".join(errors))
    today = _today()
    doc.front["verified_at"] = today
    doc.front["updated_at"] = today
    _rewrite(doc, repo)
    dest = _move(doc.path, repo.managed_dir(repo_mod.KNOWLEDGE))
    index_mod.build(repo)
    return dest


def reject(repo: repo_mod.Repo, doc_id: str, reason: str,
           human: bool = False) -> str:
    """Rejeita draft para archive com motivo registrado. Exige human."""
    if not reason.strip():
        raise ValueError("rejeição exige motivo (--reason)")
    if not human:
        raise ValueError("rejeição exige aprovação humana (--human)")
    doc = repo_mod.find_by_id(repo, doc_id)
    if doc is None:
        raise KeyError(f"id não encontrado: {doc_id}")
    if doc.status != "draft":
        raise ValueError(f"só draft pode ser rejeitado (atual: {doc.status})")
    errors = transition(doc, "archived", human=human)
    if errors:
        raise ValueError("; ".join(errors))
    doc.front["rejected_reason"] = reason.strip()
    doc.front["rejected_at"] = _today()
    _rewrite(doc, repo)
    return _move(doc.path, repo.managed_dir(repo_mod.ARCHIVE))


def archive(repo: repo_mod.Repo, doc_id: str, human: bool = False) -> str:
    if not human:
        raise ValueError("arquivamento exige aprovação humana (--human)")
    doc = repo_mod.find_by_id(repo, doc_id)
    if doc is None:
        raise KeyError(f"id não encontrado: {doc_id}")
    if doc.status not in ("verified", "stale"):
        raise ValueError(f"só verified/stale pode ser arquivado (atual: {doc.status})")
    errors = transition(doc, "archived", human=human)
    if errors:
        raise ValueError("; ".join(errors))
    doc.front["updated_at"] = _today()
    _rewrite(doc, repo)
    dest = _move(doc.path, repo.managed_dir(repo_mod.ARCHIVE))
    index_mod.build(repo)
    return dest


def mark_stale(repo: repo_mod.Repo, doc_id: str, human: bool = False) -> str:
    if not human:
        raise ValueError("marcar stale exige aprovação humana (--human)")
    doc = repo_mod.find_by_id(repo, doc_id)
    if doc is None:
        raise KeyError(f"id não encontrado: {doc_id}")
    if doc.status != "verified":
        raise ValueError(f"só verified pode virar stale (atual: {doc.status})")
    errors = transition(doc, "stale", human=human)
    if errors:
        raise ValueError("; ".join(errors))
    doc.front["updated_at"] = _today()
    _rewrite(doc, repo)
    index_mod.build(repo)
    return doc.path


def edit(repo: repo_mod.Repo, doc_id: str) -> str:
    doc = repo_mod.find_by_id(repo, doc_id)
    if doc is None:
        raise KeyError(f"id não encontrado: {doc_id}")
    editor = os.environ.get("EDITOR", "vi")
    result = subprocess.run([editor, doc.path])
    if result.returncode != 0:
        raise RuntimeError(f"editor saiu com código {result.returncode}")
    with open(doc.path, encoding="utf-8") as handle:
        updated = parse_doc(handle.read(), doc.path)
    if not updated.valid:
        raise ValueError(f"documento ficou inválido: {'; '.join(updated.errors)}")
    return doc.path
