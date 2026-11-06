"""Fila de revisão e promoção de rascunhos (plano, Fase 5, spec §6.4).

Nenhuma promoção a verified sem human=True, a não ser que o usuário tenha
ligado uma política automática em [review]. O que entra assim fica marcado
`reviewed_by: auto` e continua na fila até um humano confirmar.
"""

from __future__ import annotations

import datetime
import difflib
import os
import subprocess

from . import index as index_mod
from . import gitops
from . import repo as repo_mod
from .models import AUTO_POLICIES, REVIEW_POLICIES, parse_doc, transition

REVIEW_SOURCES = ("import", "research")


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
        elif status == "verified" and doc.front.get("reviewed_by") == "auto":
            items.append((updated, doc.id, doc.path,
                          "aprovado sem revisão; confirme com approve --human"))
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
    gitops.touch(doc_path)  # origem removida
    gitops.touch(dest)      # destino criado
    return dest


def _rewrite(doc, repo: repo_mod.Repo) -> None:
    repo_mod.save_atomic(
        doc.path, repo_mod.render_doc(doc.front, doc.body))


def approve(repo: repo_mod.Repo, doc_id: str, human: bool = False,
            policy: str = "") -> str:
    """Promove draft a verified e reindexa. Exige human=True ou política auto.

    Em verified que entrou sem revisão, human=True só confirma a revisão. Em
    stale, human=True reativa: a política automática nunca decide se algo
    desatualizado voltou a valer.
    """
    doc = repo_mod.find_by_id(repo, doc_id)
    if doc is None:
        raise KeyError(f"id não encontrado: {doc_id}")
    if not doc.valid:
        raise ValueError(f"documento inválido: {'; '.join(doc.errors)}")
    if doc.status == "verified" and doc.front.get("reviewed_by") == "auto":
        if not human:
            raise ValueError("confirmar revisão exige aprovação humana (--human)")
        doc.front["reviewed_by"] = "human"
        doc.front["updated_at"] = _today()
        _rewrite(doc, repo)
        gitops.touch(doc.path)
        index_mod.build(repo)
        return doc.path
    if doc.status == "stale":
        return _reverify(repo, doc, human)
    if doc.status != "draft":
        raise ValueError(f"só draft ou stale pode ser aprovado (atual: {doc.status})")
    errors = transition(doc, "verified", human=human, policy=policy)
    if errors:
        raise ValueError("; ".join(errors))
    today = _today()
    doc.front["verified_at"] = today
    doc.front["updated_at"] = today
    doc.front["reviewed_by"] = "human" if human else "auto"
    _rewrite(doc, repo)
    dest = _move(doc.path, repo.managed_dir(repo_mod.KNOWLEDGE))
    index_mod.build(repo)
    return dest


def _next_review(front: dict, today: str) -> str | None:
    """review_after depois de reverificar: mesmo intervalo de antes, a partir
    de hoje. None quando não há intervalo para repetir ou ele ainda vale."""
    review_after = front.get("review_after")
    verified_at = front.get("verified_at")
    if not isinstance(review_after, str) or review_after > today:
        return None
    try:
        start = datetime.date.fromisoformat(str(verified_at))
        end = datetime.date.fromisoformat(review_after)
    except ValueError:
        return None
    interval = end - start
    if interval.days <= 0:
        return None
    return (datetime.date.fromisoformat(today) + interval).isoformat()


def _reverify(repo: repo_mod.Repo, doc, human: bool) -> str:
    if not human:
        raise ValueError("reativar stale exige aprovação humana (--human)")
    errors = transition(doc, "verified", human=True)
    if errors:
        raise ValueError("; ".join(errors))
    today = _today()
    next_review = _next_review(doc.front, today)
    if next_review:
        doc.front["review_after"] = next_review
    doc.front["verified_at"] = today
    doc.front["updated_at"] = today
    doc.front["reviewed_by"] = "human"
    _rewrite(doc, repo)
    gitops.touch(doc.path)
    index_mod.build(repo)
    return doc.path


def policy_for(cfg: dict, source: str) -> str:
    """Política de [review] para a origem (import ou research)."""
    if source not in REVIEW_SOURCES:
        raise ValueError(f"origem de revisão desconhecida: {source}")
    value = cfg.get("review", {}).get(source, "human")
    if value not in REVIEW_POLICIES:
        raise ValueError(
            f"review.{source} inválido: {value!r} (use {', '.join(REVIEW_POLICIES)})")
    return value


def clean_check(repo: repo_mod.Repo, doc_id: str, source: str,
                discarded: list[str] | None = None) -> list[str]:
    """Motivos que impedem a aprovação automática em auto-if-clean.

    Pesquisa precisa de fonte web, nada sem fonte, nenhuma página descartada
    por injection e nenhum conflito. Import é conteúdo seu: só conflito.
    """
    doc = repo_mod.find_by_id(repo, doc_id)
    if doc is None:
        return [f"id não encontrado: {doc_id}"]
    if not doc.valid:
        return [f"documento inválido: {'; '.join(doc.errors)}"]
    reasons: list[str] = []
    if source == "research":
        urls = [entry for entry in doc.front.get("sources") or []
                if isinstance(entry, dict) and str(entry.get("url", "")).startswith("http")]
        if not urls:
            reasons.append("nenhuma fonte web")
        claims = unsourced_claims(doc.body)
        if claims:
            reasons.append(f"{len(claims)} trecho(s) sem fonte")
        injected = [item for item in discarded or [] if "injection" in item]
        if injected:
            reasons.append(f"{len(injected)} página(s) descartada(s) por injection")
    conflicts = possible_conflicts(repo, doc_id)
    if conflicts:
        reasons.append(f"possível conflito com {', '.join(conflicts)}")
    return reasons


def apply_policy(repo: repo_mod.Repo, cfg: dict, doc_id: str, source: str,
                 discarded: list[str] | None = None) -> dict:
    """Aplica [review] ao rascunho recém-criado.

    Retorna {"policy", "approved", "path", "reasons"}. Política human não faz
    nada; auto aprova qualquer rascunho válido; auto-if-clean só o limpo.
    """
    policy = policy_for(cfg, source)
    result = {"policy": policy, "approved": False, "path": "", "reasons": []}
    if policy not in AUTO_POLICIES:
        return result
    if policy == "auto-if-clean":
        reasons = clean_check(repo, doc_id, source, discarded)
        if reasons:
            result["reasons"] = reasons
            return result
    result["path"] = approve(repo, doc_id, human=False, policy=policy)
    result["approved"] = True
    return result


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
    with open(doc.path, "rb") as handle:
        before = handle.read()
    result = subprocess.run([editor, doc.path])
    if result.returncode != 0:
        raise RuntimeError(f"editor saiu com código {result.returncode}")
    with open(doc.path, "rb") as handle:
        after = handle.read()
    if after != before:
        gitops.touch(doc.path)
    with open(doc.path, encoding="utf-8") as handle:
        updated = parse_doc(handle.read(), doc.path)
    if not updated.valid:
        raise ValueError(f"documento ficou inválido: {'; '.join(updated.errors)}")
    return doc.path
