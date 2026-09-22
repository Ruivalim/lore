"""Configuração: .lore/config.toml sobre defaults (PLAN.md §3)."""

from __future__ import annotations

import os
import tomllib

DEFAULTS: dict = {
    "repository": {
        "knowledge_dir": "knowledge",
        "drafts_dir": "drafts",
        "archive_dir": "archive",
    },
    "retrieval": {"lexical": True, "semantic": False},
    "answer": {"mode": "local-first", "allow_extractive_fallback": True},
    "research": {"enabled": False, "require_confirmation": True},
    "privacy": {
        "redact_secrets": True,
        "send_full_documents": False,
        "auto_commit": False,
    },
}

CONFIG_TEMPLATE = """\
[repository]
knowledge_dir = "knowledge"
drafts_dir = "drafts"
archive_dir = "archive"

[retrieval]
lexical = true
semantic = false
# embedding_model = ""

[answer]
mode = "local-first"
# local_model_endpoint = ""
allow_extractive_fallback = true

[research]
enabled = false
require_confirmation = true
# search_provider = "duckduckgo"
# model_provider = "openai-compatible"
# model_endpoint = "http://localhost:11434"
# model_name = "local-model"
# extra_patterns = []

[privacy]
redact_secrets = true
send_full_documents = false
auto_commit = false
"""


def _merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load(root: str) -> tuple[dict, list[str]]:
    """Carrega config. Retorna (config, erros). Ausente = defaults, sem erro."""
    path = os.path.join(root, ".lore", "config.toml")
    if not os.path.isfile(path):
        return _merge({}, DEFAULTS), []
    try:
        with open(path, "rb") as handle:
            raw = tomllib.load(handle)
    except (tomllib.TOMLDecodeError, OSError) as exc:
        return _merge({}, DEFAULTS), [f"config inválida: {exc}"]
    if not isinstance(raw, dict):
        return _merge({}, DEFAULTS), ["config deve ser um mapa"]
    return _merge(DEFAULTS, raw), []


def init(root: str) -> str:
    """Cria .lore/config.toml a partir do template. Erro se já existir."""
    path = os.path.join(root, ".lore", "config.toml")
    if os.path.exists(path):
        raise FileExistsError(f"config já existe: {path}")
    os.makedirs(os.path.join(root, ".lore"), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(CONFIG_TEMPLATE)
    return path
