"""Documentos-semente: o próprio Lore explicado dentro do acervo.

`lore init` instala e `lore seed` instala ou atualiza em knowledge/lore/.
Atualizar nunca passa por cima do que o usuário mexeu: o hash do que foi
instalado fica em .lore/seed.json, e arquivo com hash diferente é pulado
(a não ser com force). Documento com o mesmo id em outro lugar (movido,
arquivado) também é pulado: ali a decisão já foi do usuário.
"""

from __future__ import annotations

import hashlib
import json
import os

from . import repo as repo_mod
from .models import parse_doc

SEED_DIR = os.path.join(os.path.dirname(__file__), "seed")
LANGS = ("pt", "en")
DEFAULT_LANG = "pt"
TARGET = os.path.join(repo_mod.KNOWLEDGE, "lore")
STATE = os.path.join(".lore", "seed.json")


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def shipped(lang: str) -> list[tuple[str, str, str]]:
    """(id, nome do arquivo, texto) das sementes da língua, em ordem."""
    if lang not in LANGS:
        raise ValueError(f"língua desconhecida: {lang} (use {', '.join(LANGS)})")
    base = os.path.join(SEED_DIR, lang)
    found = []
    for name in sorted(os.listdir(base)):
        if not name.endswith(".md"):
            continue
        path = os.path.join(base, name)
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        found.append((parse_doc(text, path).id, name, text))
    return found


def _load_state(root: str) -> dict:
    path = os.path.join(root, STATE)
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {"lang": "", "files": {}}
    if not isinstance(data, dict) or not isinstance(data.get("files"), dict):
        return {"lang": "", "files": {}}
    return data


def _save_state(root: str, state: dict) -> None:
    path = os.path.join(root, STATE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
        handle.write("\n")


def installed_lang(root: str) -> str:
    return str(_load_state(root).get("lang") or "")


def install(repo: repo_mod.Repo, lang: str = "", force: bool = False) -> list[dict]:
    """Instala ou atualiza as sementes. Retorna uma ação por documento.

    Ações: added, updated, unchanged, modified (pulado, você editou),
    removed (pulado, você apagou), elsewhere (pulado, o id existe fora de
    knowledge/lore/).
    """
    state = _load_state(repo.root)
    lang = lang or state.get("lang") or DEFAULT_LANG
    docs = shipped(lang)
    target_dir = os.path.join(repo.root, TARGET)
    results = []
    changed = False
    for doc_id, name, text in docs:
        dest = os.path.join(target_dir, name)
        rel = os.path.relpath(dest, repo.root)
        existing = repo_mod.find_by_id(repo, doc_id)
        if existing is not None and os.path.realpath(existing.path) != os.path.realpath(dest):
            results.append({"id": doc_id, "action": "elsewhere", "path": existing.path})
            continue
        new_hash = _hash(text)
        if not os.path.exists(dest) and rel in state["files"] and not force:
            # Já foi instalada e não está mais aí: apagar foi escolha sua.
            results.append({"id": doc_id, "action": "removed", "path": dest})
            continue
        if not os.path.exists(dest):
            action = "added"
        else:
            with open(dest, encoding="utf-8") as handle:
                current = _hash(handle.read())
            if current == new_hash:
                state["files"][rel] = new_hash
                results.append({"id": doc_id, "action": "unchanged", "path": dest})
                continue
            if current != state["files"].get(rel) and not force:
                results.append({"id": doc_id, "action": "modified", "path": dest})
                continue
            action = "updated"
        os.makedirs(target_dir, exist_ok=True)
        repo_mod.save_atomic(dest, text)
        state["files"][rel] = new_hash
        changed = True
        results.append({"id": doc_id, "action": action, "path": dest})
    state["lang"] = lang
    _save_state(repo.root, state)
    if changed:
        from . import index as index_mod

        index_mod.build(repo)
    return results
