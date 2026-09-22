"""CLI lore: argparse, stdlib only (PLAN.md §0)."""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys

from . import config as config_mod
from . import repo as repo_mod
from .models import TYPES, parse_doc

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "templates")


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
    _out({"ok": True, "message": dest, "id": doc_id, "path": dest}, args.json)
    return 0


def cmd_add(args, repo: repo_mod.Repo) -> int:
    try:
        dest = repo_mod.add_file(repo, args.arquivo, args.to, args.move)
    except (ValueError, FileNotFoundError, OSError) as exc:
        return _err(str(exc), args.json)
    _out({"ok": True, "message": dest, "path": dest}, args.json)
    return 0


def cmd_search(args, repo: repo_mod.Repo) -> int:
    from .retrieve import IndexMissingError, search

    try:
        hits = search(repo, args.termos, args.limit, args.type or "", args.tag or "")
    except IndexMissingError as exc:
        return _err(str(exc), args.json)
    except ValueError as exc:
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
    _out(
        {"ok": True,
         "message": f"indexados {stats['docs']} docs, {stats['chunks']} trechos",
         **stats},
        args.json,
    )
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


def run_doctor(repo: repo_mod.Repo) -> tuple[list[str], list[str]]:
    """Retorna (problemas, avisos)."""
    problems: list[str] = []
    warnings: list[str] = []
    cfg, cfg_errors = config_mod.load(repo.root)
    problems.extend(f"config: {err}" for err in cfg_errors)

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
    _ = cfg
    return problems, warnings


def cmd_doctor(args, repo: repo_mod.Repo) -> int:
    problems, warnings = run_doctor(repo)
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
            path = config_mod.init(repo.root)
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


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default="", help="raiz do repositório lore")
    common.add_argument("--json", action="store_true", help="saída estruturada")
    # Nos subparsers, SUPPRESS impede default de apagar flag passada antes.
    common_sub = argparse.ArgumentParser(add_help=False)
    common_sub.add_argument("--root", default=argparse.SUPPRESS)
    common_sub.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    parser = argparse.ArgumentParser(
        prog="lore", description="Biblioteca pessoal curada", parents=[common]
    )
    sub = parser.add_subparsers(dest="command", required=True)
    _orig_add = sub.add_parser
    sub.add_parser = lambda *a, **k: _orig_add(*a, parents=[common_sub], **k)

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

    p_show = sub.add_parser("show", help="exibir documento por id")
    p_show.add_argument("id")
    p_show.set_defaults(func=cmd_show)

    p_search = sub.add_parser("search", help="buscar na base local")
    p_search.add_argument("termos")
    p_search.add_argument("--limit", type=int, default=10)
    p_search.add_argument("--type", default="")
    p_search.add_argument("--tag", default="")
    p_search.set_defaults(func=cmd_search)
    sub.add_parser("ask", help="perguntar à base (Fase 3)").set_defaults(
        func=lambda args, repo: _err("ask chega na Fase 3", args.json)
    )
    sub.add_parser("review", help="fila de revisão (Fase 5)").set_defaults(
        func=lambda args, repo: _err("review chega na Fase 5", args.json)
    )
    p_reindex = sub.add_parser("reindex", help="reconstruir índice")
    p_reindex.set_defaults(func=cmd_reindex)

    p_doctor = sub.add_parser("doctor", help="diagnosticar repositório")
    p_doctor.set_defaults(func=cmd_doctor)

    p_config = sub.add_parser("config", help="ver ou iniciar configuração")
    p_config.add_argument("--init", action="store_true")
    p_config.set_defaults(func=cmd_config)

    for name in ("approve", "reject", "archive", "stale"):
        sub.add_parser(name, help=f"{name} (Fase 5)").set_defaults(
            func=lambda args, repo, _n=name: _err(f"{_n} chega na Fase 5", args.json)
        )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root) if args.root else repo_mod.find_root()
    repo = repo_mod.Repo(root)
    return args.func(args, repo)


if __name__ == "__main__":
    raise SystemExit(main())
