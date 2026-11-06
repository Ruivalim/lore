"""CLI lore: argparse, stdlib only (plan §0)."""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import sys

from . import config as config_mod
from . import gitops
from . import repo as repo_mod
from .models import TYPES, parse_doc

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")


def _auto_commit(repo: repo_mod.Repo, action: str, subject: str) -> None:
    """Commit dos paths tocados pela operação, se [git] auto_commit.

    Nunca faz pull/rebase. Falha de git/rede é silenciosa aqui: o comando já
    teve sucesso, o push fica pendente e `lore doctor` o denuncia.
    """
    cfg, _ = config_mod.load(repo.root)
    if not gitops.auto_commit_enabled(cfg):
        return
    paths = gitops.touched_paths()
    gitops.clear_touched()
    if not paths:
        return
    try:
        gitops.commit_paths(repo.root, paths, action, subject)
    except gitops.GitError:
        pass


def _apply_review(repo: repo_mod.Repo, cfg: dict, doc_id: str, source: str,
                  discarded: list[str] | None = None) -> dict:
    """[review] no rascunho novo. Erro de política vira aviso: o rascunho fica."""
    from . import review as review_mod

    try:
        return review_mod.apply_policy(repo, cfg, doc_id, source, discarded)
    except (KeyError, ValueError) as exc:
        return {"policy": "", "approved": False, "path": "", "reasons": [str(exc)]}


def _review_message(review: dict) -> str:
    if review.get("approved"):
        return (f"aprovado automaticamente (review = {review['policy']}): "
                f"{review['path']}\nconfirme depois com: lore approve <id> --human")
    if review.get("reasons"):
        return "ficou em rascunho: " + "; ".join(review["reasons"])
    return ""


def _today() -> str:
    return datetime.date.today().isoformat()


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "sem-titulo"


def _out(payload: dict | str, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif isinstance(payload, dict):
        print(payload.get("message", json.dumps(payload, ensure_ascii=False)))
    else:
        print(payload)


def _err(message: str, as_json: bool) -> int:
    if as_json:
        print(json.dumps({"ok": False, "error": message}, ensure_ascii=False))
    else:
        print(f"erro: {message}", file=sys.stderr)
    return 1


def cmd_new(args, repo: repo_mod.Repo) -> int:
    template_path = os.path.normpath(
        os.path.join(TEMPLATE_DIR, f"{args.type}.md")
    )
    if not os.path.isfile(template_path):
        return _err(f"template ausente: {args.type}", args.json)
    with open(template_path, encoding="utf-8") as handle:
        template = handle.read()
    doc_id = args.id or _slug(args.title)
    today = _today()
    text = (
        template.replace("<slug-unico>", doc_id)
        .replace("<Título humano>", args.title)
        .replace("<YYYY-MM-DD>", today)
    )
    # Título dentro do corpo: só a primeira ocorrência após o front matter.
    dest = repo_mod._safe_join(
        repo.root, repo_mod.DRAFTS, f"{doc_id}.md"
    )
    if os.path.exists(dest):
        return _err(f"rascunho já existe: {dest}", args.json)
    doc = parse_doc(text, dest)
    if not doc.valid:
        return _err(f"template gerou doc inválido: {'; '.join(doc.errors)}", args.json)
    repo_mod.save_atomic(dest, text)
    _auto_commit(repo, "new", doc_id)
    _out({"ok": True, "message": dest, "id": doc_id, "path": dest}, args.json)
    return 0


def cmd_add(args, repo: repo_mod.Repo) -> int:
    try:
        dest = repo_mod.add_file(repo, args.arquivo, args.to, args.move)
    except (ValueError, FileNotFoundError, OSError) as exc:
        return _err(str(exc), args.json)
    _auto_commit(repo, "add", os.path.basename(dest))
    _out({"ok": True, "message": dest, "path": dest}, args.json)
    return 0


def cmd_import(args, repo: repo_mod.Repo) -> int:
    from .importer import import_markdown

    cfg, errors = config_mod.load(repo.root)
    if errors:
        return _err("; ".join(errors), args.json)
    try:
        result = import_markdown(repo, args.arquivo, cfg)
    except (TypeError, ValueError, FileNotFoundError, OSError, RuntimeError) as exc:
        return _err(str(exc), args.json)
    review = _apply_review(repo, cfg, result.doc_id, "import")
    _auto_commit(repo, "import", result.doc_id)
    message = f"importado como draft: {result.path}"
    if review["approved"] or review["reasons"]:
        message += "\n" + _review_message(review)
    payload = {
        "ok": True,
        "id": result.doc_id,
        "title": result.title,
        "type": result.doc_type,
        "tags": result.tags,
        "summary": result.summary,
        "status": "verified" if review["approved"] else "draft",
        "path": review["path"] or result.path,
        "review": review,
        "message": message,
    }
    _out(payload, args.json)
    return 0


def _resolve_semantic(args, repo: repo_mod.Repo):
    """Retorna (usar_semantico, embedder). Kill switch: --lexical ou config false."""
    from . import config as config_mod

    cfg, _ = config_mod.load(repo.root)
    rcfg = cfg.get("retrieval", {})
    use = bool(getattr(args, "semantic", False)) or bool(rcfg.get("semantic", False))
    if getattr(args, "lexical", False):
        use = False
    if not use:
        return False, None
    from .semantic import EndpointEmbedder, HashEmbedder

    if rcfg.get("embedding_backend") == "endpoint" and rcfg.get("embedding_endpoint"):
        return True, EndpointEmbedder(
            rcfg["embedding_endpoint"], rcfg.get("embedding_model", ""),
            os.environ.get("LORE_API_KEY", ""))
    return True, HashEmbedder()


def _retrieval_weights(repo: repo_mod.Repo) -> tuple[float, float]:
    from . import config as config_mod

    cfg, _ = config_mod.load(repo.root)
    rcfg = cfg.get("retrieval", {})
    return (float(rcfg.get("lex_weight", 0.7)),
            float(rcfg.get("sem_weight", 0.3)))


def cmd_search(args, repo: repo_mod.Repo) -> int:
    from .retrieve import IndexMissingError, search

    use_sem, embedder = _resolve_semantic(args, repo)
    try:
        if use_sem:
            from .retrieve import search_hybrid

            lex_w, sem_w = _retrieval_weights(repo)
            hits = search_hybrid(repo, args.termos, embedder, args.limit,
                                 args.type or "", args.tag or "",
                                 lex_w, sem_w)
        else:
            hits = search(repo, args.termos, args.limit, args.type or "", args.tag or "")
    except IndexMissingError as exc:
        return _err(str(exc), args.json)
    except ValueError as exc:
        return _err(str(exc), args.json)
    except RuntimeError as exc:
        return _err(str(exc), args.json)
    if args.json:
        _out({"ok": True, "hits": [hit.__dict__ for hit in hits]}, True)
        return 0
    if not hits:
        print("nada encontrado")
        return 0
    for pos, hit in enumerate(hits, 1):
        section = f"#{hit.heading}" if hit.heading else ""
        why = ", ".join(hit.matched_in) or "?"
        stale = " [stale]" if hit.status == "stale" else ""
        print(f"{pos}. {hit.path}{section}{stale}")
        print(f"   {hit.title} (via: {why})")
        if hit.snippet:
            print(f"   {hit.snippet}")
    return 0


def cmd_reindex(args, repo: repo_mod.Repo) -> int:
    from .index import build

    stats = build(repo)
    if getattr(args, "semantic", False):
        from .semantic import HashEmbedder, build_vectors

        _, embedder = _resolve_semantic(args, repo)
        stats.update(build_vectors(repo, embedder or HashEmbedder()))
        stats["message"] = (f"indexados {stats['docs']} docs, "
                              f"{stats['chunks']} trechos, "
                              f"{stats['vectors']} vetores")
    else:
        stats["message"] = (f"indexados {stats['docs']} docs, "
                              f"{stats['chunks']} trechos")
    _out({"ok": True, **stats}, args.json)
    return 0


def cmd_list(args, repo: repo_mod.Repo) -> int:
    docs = []
    for doc in repo_mod.load_all(repo):
        docs.append({
            "id": doc.id,
            "title": str(doc.front.get("title", "")),
            "type": str(doc.front.get("type", "")),
            "status": doc.status,
            "tags": [str(tag) for tag in doc.front.get("tags") or []],
            "updated_at": str(doc.front.get("updated_at") or ""),
            "path": os.path.relpath(doc.path, repo.root),
            "valid": doc.valid,
            "reviewed_by": str(doc.front.get("reviewed_by") or ""),
        })
    if args.json:
        _out({"ok": True, "docs": docs}, True)
        return 0
    for item in docs:
        print(f"{item['status']:<9} {item['type']:<9} {item['id']}  {item['title']}")
    return 0


def find_tui() -> str:
    """Binário do TUI: $LORE_TUI, senão lore-tui no PATH."""
    explicit = os.environ.get("LORE_TUI", "")
    if explicit:
        return explicit if os.access(explicit, os.X_OK) else ""
    return shutil.which("lore-tui") or ""


def open_tui(args, repo: repo_mod.Repo) -> int:
    binary = find_tui()
    if not binary:
        return _err("lore-tui não encontrado; rode `make tui-install` "
                    "ou aponte LORE_TUI para o binário", args.json)
    if args.json or not sys.stdin.isatty() or not sys.stdout.isatty():
        return _err("o TUI precisa de terminal; passe a pergunta: lore ask \"...\"",
                    args.json)
    lore_bin = shutil.which(sys.argv[0]) or os.path.abspath(sys.argv[0])
    os.execv(binary, [binary, "--root", repo.root, "--lore", lore_bin])
    return 0  # não volta


def cmd_ask(args, repo: repo_mod.Repo) -> int:
    from .answer import ask as run_ask

    if not args.pergunta:
        return open_tui(args, repo)
    if args.yes:
        cfg, _ = config_mod.load(repo.root)
        problem = _research_problem(cfg)
        if problem:
            return _err(f"--yes exige pesquisa utilizável: {problem}", args.json)
    if args.as_of and not re.match(r"^\d{4}-\d{2}-\d{2}$", args.as_of):
        return _err("--as-of exige data YYYY-MM-DD", args.json)
    answer = run_ask(
        repo, args.pergunta, doc_type=args.type or "", tag=args.tag or "",
        as_of=args.as_of or "", local_only=args.local_only,
        extractive=args.extractive,
        semantic=_resolve_semantic(args, repo)[0],
        embedder=_resolve_semantic(args, repo)[1],
        lex_weight=_retrieval_weights(repo)[0],
        sem_weight=_retrieval_weights(repo)[1],
    )
    payload = {
        "ok": True,
        "coverage": answer.coverage,
        "short": answer.short,
        "text": answer.text,
        "citations": answer.citations,
        "gap": answer.gap,
        "warning": answer.warning,
        "researched": False,
        "research": None,
    }
    if not args.json:
        sys.stdout.write(_relative(repo, _short_or_full(answer.short, answer.text,
                                                       args.full)))
    if (
        answer.coverage in ("insufficient", "partial")
        and not args.local_only
    ):
        code, research_payload, researched = _maybe_research(
            args, repo, args.pergunta, answer
        )
        payload["ok"] = code == 0
        payload["researched"] = researched
        payload["research"] = research_payload
        if args.json:
            _out(payload, True)
        return code
    if args.json:
        _out(payload, True)
    return 0


FULL_HINT = "(resposta completa: lore ask --full)"


def _relative(repo: repo_mod.Repo, text: str) -> str:
    """Caminhos do acervo relativos à raiz, só para leitura no terminal."""
    return text.replace(os.path.join(repo.root, ""), "")


def _short_or_full(short: str, full: str, want_full: bool) -> str:
    """Curta por padrão; a completa com --full ou quando não há curta."""
    if want_full or not short.strip():
        return full if full.endswith("\n") else full + "\n"
    return f"{short.strip()}\n\n{FULL_HINT}\n"


RESEARCH_MODES = ("web", "agent")
# Agentes que pesquisam sozinhos (web + base). Os demais só redigem no modo web.
RESEARCH_AGENTS = ("claude",)


def _research_problem(cfg: dict) -> str:
    """Motivo pelo qual a pesquisa não pode rodar, ou '' se pode."""
    from . import agents as agents_mod

    rcfg = cfg.get("research", {})
    if not rcfg.get("enabled"):
        return "research.enabled = false"
    mode = rcfg.get("mode", "web")
    if mode not in RESEARCH_MODES:
        return f"research.mode desconhecido ({mode}); use web ou agent"
    try:
        agent = agents_mod.resolve(cfg, "research")
    except ValueError as exc:
        return str(exc)
    if mode == "agent" and agent.name not in RESEARCH_AGENTS:
        return (f"research.mode = agent só funciona com {', '.join(RESEARCH_AGENTS)} "
                f"(agente de research: {agent.name})")
    return ""


def _maybe_research(args, repo: repo_mod.Repo, question: str, answer):
    from . import agents as agents_mod
    from .research import (
        WEB_SEARCHES,
        AgentModel,
        ClaudeAgent,
        research,
        research_agent,
    )

    cfg, _ = config_mod.load(repo.root)
    rcfg = cfg.get("research", {})
    if not rcfg.get("enabled"):
        return 0, None, False
    problem = _research_problem(cfg)
    if problem:
        message = f"pesquisa indisponível ({problem}); pergunta preservada."
        if not args.json:
            print(message)
        return 1, {"ok": False, "error": message}, False
    agent = agents_mod.resolve(cfg, "research")
    confirmed = args.yes or not rcfg.get("require_confirmation", True)
    if not confirmed and args.json:
        message = "--json não pergunta; use --yes para pesquisar externamente."
        return 0, {"ok": False, "error": message}, False
    if not confirmed:
        from .countdown import confirm

        confirmed = confirm("Pesquisar externamente e criar um rascunho?",
                            float(rcfg.get("confirm_timeout", 5)))
    if not confirmed:
        return 0, None, False
    local_context = "\n\n".join(
        f"[fonte local: {citation}]\n{text}"
        for citation, text in answer.context[:3]
    )
    if rcfg.get("mode", "web") == "agent":
        if not args.json:
            print(f"Pesquisando com {agent.name} (web e base Lore)…", flush=True)
        researcher = ClaudeAgent(
            binary=agent.binary or "claude",
            model=agent.model,
            max_budget_usd=float(rcfg.get("max_budget_usd", 0) or 0),
            cwd=repo.root,
            extra_instructions=str(rcfg.get("extra_instructions", "") or ""),
        )
        result = research_agent(repo, question, local_context, agent=researcher,
                                extra_patterns=cfg.get("privacy", {}).get("extra_patterns", []))
    else:
        web_cls = WEB_SEARCHES.get(rcfg.get("search_provider", "duckduckgo"),
                                   WEB_SEARCHES["duckduckgo"])
        result = research(repo, question, local_context, web=web_cls(),
                          model=AgentModel(agent),
                          extra_patterns=cfg.get("privacy", {}).get("extra_patterns", []))
    result_payload = {
        "ok": result.ok,
        "answer": result.answer,
        "summary": result.summary,
        "draft_path": result.draft_path,
        "sources": [source.__dict__ for source in result.sources],
        "blocked": result.blocked,
        "error": result.error,
        "discarded": result.discarded,
    }
    if result.blocked:
        if not args.json:
            print(f"bloqueado: {result.blocked}")
        return 1, result_payload, True
    if not result.ok:
        if not args.json:
            print(result.error)
        return 1, result_payload, True
    review = None
    if result.ok and result.draft_path:
        doc_id = os.path.splitext(os.path.basename(result.draft_path))[0]
        review = _apply_review(repo, cfg, doc_id, "research", result.discarded)
        result_payload["review"] = review
        if review["approved"]:
            result_payload["draft_path"] = review["path"]
    if not args.json:
        print()
        if args.full or not result.summary:
            print(result.answer)
        else:
            print("Resposta externa, ainda não verificada.")
            print(f"Rascunho salvo em:\n  {result.draft_path}\n")
            print(f"{result.summary}\n\n{FULL_HINT}")
        if review and (review["approved"] or review["reasons"]):
            print(_review_message(review))
        for item in result.discarded:
            print(f"descartada: {item}")
    return 0, result_payload, True


def cmd_review(args, repo: repo_mod.Repo) -> int:
    from . import review as review_mod

    if not args.id:
        items = review_mod.queue(repo)
        if args.json:
            _out({"ok": True, "queue": [
                {"id": doc_id, "path": path, "reason": reason}
                for doc_id, path, reason in items]}, True)
            return 0
        if not items:
            print("fila vazia")
            return 0
        for doc_id, path, reason in items:
            print(f"- {doc_id} ({reason}): {path}")
        return 0
    try:
        info = review_mod.detail(repo, args.id)
    except KeyError as exc:
        return _err(str(exc), args.json)
    if args.json:
        _out({"ok": True, **info}, True)
        return 0
    print(f"id: {info['id']}\nlocal: {info['path']}")
    print(f"status: {info['front'].get('status')}  "
          f"tipo: {info['front'].get('type')}")
    print("fontes:")
    for src in info["front"].get("sources", []):
        if isinstance(src, dict) and src.get("kind") == "local":
            print(f"  - arquivo local: {src.get('path', '?')} ({src.get('description', '')})")
        else:
            print(f"  - {src}")
    if info["unsourced_claims"]:
        print("alegações sem fonte:")
        for claim in info["unsourced_claims"]:
            print(f"  ! {claim}")
    if info["possible_conflicts"]:
        print("possíveis conflitos:")
        for item in info["possible_conflicts"]:
            print(f"  ? {item}")
    if info["diff"]:
        print("diff contra versão anterior:")
        print(info["diff"])
    print()
    with open(info["path"], encoding="utf-8") as handle:
        sys.stdout.write(handle.read())
    return 0


def cmd_edit(args, repo: repo_mod.Repo) -> int:
    from . import review as review_mod

    try:
        path = review_mod.edit(repo, args.id)
    except (KeyError, ValueError, RuntimeError, OSError) as exc:
        return _err(str(exc), args.json)
    _auto_commit(repo, "edit", args.id)
    _out({"ok": True, "message": f"documento editado: {path}", "path": path}, args.json)
    return 0


def _state_change(args, repo, action: str) -> int:
    from . import review as review_mod

    funcs = {
        "approve": lambda: review_mod.approve(repo, args.id, args.human),
        "reject": lambda: review_mod.reject(repo, args.id, args.reason or "",
                                              args.human),
        "archive": lambda: review_mod.archive(repo, args.id, args.human),
        "stale": lambda: review_mod.mark_stale(repo, args.id, args.human),
    }
    try:
        dest = funcs[action]()
    except (KeyError, ValueError, RuntimeError) as exc:
        return _err(str(exc), args.json)
    _auto_commit(repo, action, args.id)
    _out({"ok": True, "message": dest, "path": dest}, args.json)
    return 0


def cmd_show(args, repo: repo_mod.Repo) -> int:
    doc = repo_mod.find_by_id(repo, args.id)
    if doc is None:
        return _err(f"id não encontrado: {args.id}", args.json)
    if args.json:
        _out({"ok": True, "front": doc.front, "body": doc.body, "path": doc.path}, True)
        return 0
    with open(doc.path, encoding="utf-8") as handle:
        sys.stdout.write(handle.read())
    return 0


def _check_links(repo: repo_mod.Repo, docs: list) -> list[str]:
    problems: list[str] = []
    ids = {doc.id.lower() for doc in docs if doc.id}
    link_re = re.compile(r"\[\[[^\]]+\]\]|\[[^\]]*\]\(([^)]+)\)")
    for doc in docs:
        for match in link_re.finditer(doc.body):
            target = match.group(0)
            if target.startswith("[["):
                ref = target[2:-2].strip().lower()
            else:
                url = (match.group(1) or "").strip()
                if url.startswith(("http://", "https://", "#", "mailto:")):
                    continue
                ref = re.sub(r"#.*$", "", url).removesuffix(".md").strip().lower()
                ref = os.path.basename(ref)
            if ref and ref not in ids:
                problems.append(f"{doc.path}: link para id inexistente: {ref}")
    return problems


def _check_agents(cfg: dict, probe: bool) -> tuple[list[str], list[str]]:
    """Agente de cada tarefa: definição válida, binário no PATH e, com probe,
    uma chamada real (CLI que sai 0 com erro só se pega chamando)."""
    from . import agents as agents_mod

    problems: list[str] = []
    warnings: list[str] = []
    seen: dict[tuple[str, str], str] = {}
    research_on = bool(cfg.get("research", {}).get("enabled"))
    for task in agents_mod.TASKS:
        if task == "research" and not research_on:
            continue
        try:
            agent = agents_mod.resolve(cfg, task)
        except ValueError as exc:
            problems.append(f"llm.{task}: {exc}")
            continue
        label = agent.name + (f" ({agent.model})" if agent.model else "")
        key = (agent.name, agent.model)
        if key in seen:
            continue
        seen[key] = task
        if agent.kind == "cli" and not shutil.which(agent.executable()):
            warnings.append(f"llm.{task}: binário de {label} não encontrado no PATH")
            continue
        if probe:
            try:
                agent.complete("Responda apenas: ok")
            except agents_mod.AgentError as exc:
                problems.append(f"llm.{task}: {label} não respondeu ({exc})")
    return problems, warnings


def run_doctor(repo: repo_mod.Repo, probe: bool = False) -> tuple[list[str], list[str]]:
    """Retorna (problemas, avisos)."""
    problems: list[str] = []
    warnings: list[str] = []
    cfg, cfg_errors = config_mod.load(repo.root)
    problems.extend(f"config: {err}" for err in cfg_errors)
    warnings.extend(f"config: chave desconhecida, ignorada: {item}"
                    for item in config_mod.config_warnings(repo.root))
    from . import review as review_mod

    for source in review_mod.REVIEW_SOURCES:
        try:
            review_mod.policy_for(cfg, source)
        except ValueError as exc:
            problems.append(f"config: {exc}")
    agent_problems, agent_warnings = _check_agents(cfg, probe)
    problems.extend(agent_problems)
    warnings.extend(agent_warnings)

    docs = repo_mod.load_all(repo)
    for doc in docs:
        for err in doc.errors:
            problems.append(f"{doc.path}: {err}")

    for doc_id, paths in repo_mod.duplicate_ids(repo).items():
        problems.append(f"id duplicado '{doc_id}': {', '.join(paths)}")

    problems.extend(_check_links(repo, [doc for doc in docs if doc.valid]))

    today = _today()
    for doc in docs:
        if not doc.valid:
            continue
        if not doc.front.get("sources") and doc.front.get("type") != "note":
            warnings.append(f"{doc.path}: sem sources")
        review_after = doc.front.get("review_after")
        if (
            isinstance(review_after, str)
            and review_after < today
            and doc.front.get("status") == "verified"
        ):
            warnings.append(f"{doc.path}: vencido (review_after {review_after})")

    from .index import is_stale

    if is_stale(repo):
        warnings.append("índice ausente ou dessincronizado; rode: lore reindex")

    if gitops.auto_commit_enabled(cfg) and gitops.is_git_repo(repo.root):
        ahead = gitops.pending_push(repo.root)
        if ahead:
            warnings.append(
                f"{ahead} commit(s) local(is) não enviado(s); rode: lore-sync ou git push"
            )
    _ = cfg
    return problems, warnings


def cmd_doctor(args, repo: repo_mod.Repo) -> int:
    problems, warnings = run_doctor(repo, probe=args.probe)
    if args.json:
        _out(
            {"ok": not problems, "problems": problems, "warnings": warnings},
            True,
        )
        return 1 if problems else 0
    for item in problems:
        print(f"ERRO: {item}")
    for item in warnings:
        print(f"aviso: {item}")
    if not problems and not warnings:
        print("ok: nenhum problema")
    elif not problems:
        print(f"ok: {len(warnings)} aviso(s), nenhum erro")
    else:
        print(f"{len(problems)} erro(s), {len(warnings)} aviso(s)")
    return 1 if problems else 0


def cmd_config(args, repo: repo_mod.Repo) -> int:
    if args.init:
        try:
            path = config_mod.init_global() if args.global_config else config_mod.init(repo.root)
        except FileExistsError as exc:
            return _err(str(exc), args.json)
        _out({"ok": True, "message": path, "path": path}, args.json)
        return 0
    cfg, errors = config_mod.load(repo.root)
    if errors:
        return _err("; ".join(errors), args.json)
    if args.json:
        _out({"ok": True, "config": cfg}, True)
    else:
        for section, values in cfg.items():
            print(f"[{section}]")
            for key, value in values.items():
                print(f"{key} = {value!r}")
    return 0


def cmd_init(args) -> int:
    try:
        result = repo_mod.init_repo(args.caminho, git=not args.no_git)
    except (FileExistsError, ValueError, OSError, gitops.GitError) as exc:
        return _err(str(exc), args.json)
    root = result["root"]
    message = f"acervo criado em {root}"
    if result["git_initialized"]:
        message += " (git init)"
    if not args.no_seed:
        from . import seed as seed_mod

        try:
            seeded = seed_mod.install(repo_mod.Repo(root), args.lang)
        except (ValueError, OSError) as exc:
            return _err(f"acervo criado, mas as sementes falharam: {exc}", args.json)
        result["seed"] = seeded
        message += (f"\n{len(seeded)} documentos sobre o próprio Lore em "
                    f"{seed_mod.TARGET}/ (tire com --no-seed)")
    if config_mod.global_repository_root() != root:
        message += (
            "\npara usar fora dele, aponte repository.root para este caminho em "
            f"{config_mod.global_config_path()}"
        )
    _out({"ok": True, "message": message, **result}, args.json)
    return 0


SEED_LABELS = {
    "added": "adicionado",
    "updated": "atualizado",
    "unchanged": "sem mudança",
    "modified": "pulado, você editou (--force sobrescreve)",
    "removed": "pulado, você apagou (--force reinstala)",
    "elsewhere": "pulado, o id existe em outro lugar",
    "replaced": "removido, trocado pela outra língua",
    "kept": "mantido na língua anterior, você editou",
}


def cmd_seed(args, repo: repo_mod.Repo) -> int:
    from . import seed as seed_mod

    try:
        results = seed_mod.install(repo, args.lang or "", force=args.force)
    except (ValueError, OSError) as exc:
        return _err(str(exc), args.json)
    _auto_commit(repo, "seed", f"documentos do Lore ({seed_mod.installed_lang(repo.root)})")
    if args.json:
        _out({"ok": True, "lang": seed_mod.installed_lang(repo.root),
              "results": results}, True)
        return 0
    for item in results:
        print(f"{item['id']}: {SEED_LABELS[item['action']]}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default="", help="raiz do repositório lore")
    common.add_argument("--json", action="store_true", help="saída estruturada")
    # Nos subparsers, SUPPRESS impede default de apagar flag passada antes.
    common_sub = argparse.ArgumentParser(add_help=False)
    common_sub.add_argument("--root", default=argparse.SUPPRESS)
    common_sub.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    from . import __version__

    parser = argparse.ArgumentParser(
        prog="lore", description="Biblioteca pessoal curada", parents=[common]
    )
    parser.add_argument("--version", action="version", version=f"lore {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    _orig_add = sub.add_parser
    sub.add_parser = lambda *a, **k: _orig_add(*a, parents=[common_sub], **k)

    p_init = sub.add_parser("init", help="criar um acervo novo")
    p_init.add_argument("caminho", nargs="?", default=".")
    p_init.add_argument("--no-git", action="store_true", help="não roda git init")
    p_init.add_argument("--no-seed", action="store_true",
                        help="não instala os documentos sobre o próprio Lore")
    p_init.add_argument("--lang", default="", choices=["", "pt", "en"],
                        help="língua dos documentos sobre o Lore (padrão pt)")

    p_seed = sub.add_parser("seed", help="instalar ou atualizar os documentos sobre o Lore")
    p_seed.add_argument("--lang", default="", choices=["", "pt", "en"],
                        help="padrão: a já instalada, senão pt")
    p_seed.add_argument("--force", action="store_true",
                        help="sobrescreve o que você editou e reinstala o que apagou")
    p_seed.set_defaults(func=cmd_seed)
    p_init.set_defaults(func=cmd_init, needs_repo=False)

    p_new = sub.add_parser("new", help="criar rascunho a partir de template")
    p_new.add_argument("--type", required=True, choices=TYPES)
    p_new.add_argument("--title", required=True)
    p_new.add_argument("--id", default="")
    p_new.set_defaults(func=cmd_new)

    p_add = sub.add_parser("add", help="importar Markdown externo")
    p_add.add_argument("arquivo")
    p_add.add_argument("--to", default="drafts", choices=list(repo_mod.MANAGED_DIRS))
    p_add.add_argument("--move", action="store_true")
    p_add.set_defaults(func=cmd_add)

    p_import = sub.add_parser("import", help="importar Markdown com metadados sugeridos pelo agente")
    p_import.add_argument("arquivo")
    p_import.set_defaults(func=cmd_import)

    p_show = sub.add_parser("show", help="exibir documento por id")
    p_show.add_argument("id")
    p_show.set_defaults(func=cmd_show)

    p_search = sub.add_parser("search", help="buscar na base local")
    p_search.add_argument("termos")
    p_search.add_argument("--limit", type=int, default=10)
    p_search.add_argument("--type", default="")
    p_search.add_argument("--tag", default="")
    p_search.set_defaults(func=cmd_search)
    p_ask = sub.add_parser("ask", help="perguntar à base local")
    p_ask.add_argument("pergunta", nargs="?", default="",
                       help="sem pergunta, abre o TUI")
    p_ask.add_argument("--local-only", action="store_true")
    p_ask.add_argument("--extractive", action="store_true",
                       help="não usa modelo para síntese")
    p_ask.add_argument("--type", default="")
    p_ask.add_argument("--tag", default="")
    p_ask.add_argument("--as-of", default="")
    p_ask.add_argument("--yes", action="store_true")
    p_ask.add_argument("--full", action="store_true",
                       help="mostra a resposta completa em vez da curta")
    p_ask.set_defaults(func=cmd_ask)
    p_list = sub.add_parser("list", help="listar documentos")
    p_list.set_defaults(func=cmd_list)
    p_reindex = sub.add_parser("reindex", help="reconstruir índice")
    p_reindex.set_defaults(func=cmd_reindex)
    for flag_holder in (p_search, p_ask, p_reindex):
        flag_holder.add_argument("--semantic", action="store_true",
                                 help="liga busca semântica (se vetores existirem)")
        flag_holder.add_argument("--lexical", action="store_true",
                                 help="força busca textual pura")
    p_review = sub.add_parser("review", help="fila de revisão ou detalhe")
    p_review.add_argument("id", nargs="?")
    p_review.set_defaults(func=cmd_review)

    p_edit = sub.add_parser("edit", help="editar documento com $EDITOR")
    p_edit.add_argument("id")
    p_edit.set_defaults(func=cmd_edit)

    p_doctor = sub.add_parser("doctor", help="diagnosticar repositório")
    p_doctor.add_argument("--probe", action="store_true",
                          help="chama cada agente configurado com um prompt mínimo")
    p_doctor.set_defaults(func=cmd_doctor)

    p_config = sub.add_parser("config", help="ver ou iniciar configuração")
    p_config.add_argument("--init", action="store_true")
    p_config.add_argument("--global", dest="global_config", action="store_true",
                          help="usar ~/.config/lore/config.yaml")
    p_config.set_defaults(func=cmd_config)

    for name in ("approve", "reject", "archive", "stale"):
        p_state = sub.add_parser(name, help=f"{name} um documento")
        p_state.add_argument("id")
        p_state.add_argument("--human", action="store_true",
                             help="aprovação humana explícita")
        p_state.add_argument("--reason", default="",
                             help="motivo (obrigatório em reject)")
        p_state.set_defaults(
            func=lambda args, repo, _n=name: _state_change(args, repo, _n))
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "needs_repo", True):
        return args.func(args)
    try:
        root = repo_mod.resolve_root(
            explicit=args.root,
            configured=config_mod.global_repository_root(),
        )
    except ValueError as exc:
        if args.command == "config" and args.global_config and args.init:
            root = os.path.abspath(args.root or os.getcwd())
        else:
            return _err(str(exc), args.json)
    repo = repo_mod.Repo(root)
    return args.func(args, repo)


if __name__ == "__main__":
    raise SystemExit(main())
