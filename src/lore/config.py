"""Configuração global YAML e configuração por repositório TOML."""

from __future__ import annotations

import os
import tomllib

import yaml

DEFAULTS: dict = {
    "repository": {
        "root": "",
        "knowledge_dir": "knowledge",
        "drafts_dir": "drafts",
        "archive_dir": "archive",
    },
    "retrieval": {
        "lexical": True,
        "semantic": False,
        "lex_weight": 0.7,
        "sem_weight": 0.3,
    },
    "answer": {"mode": "local-first", "allow_extractive_fallback": True},
    "research": {"enabled": False, "require_confirmation": True,
                 "confirm_timeout": 5},
    "privacy": {
        "redact_secrets": True,
        "send_full_documents": False,
    },
    "git": {"auto_commit": False},
    "pi": {"binary": "pi", "model": ""},
}

CONFIG_TEMPLATE = """\
[repository]
knowledge_dir = "knowledge"
drafts_dir = "drafts"
archive_dir = "archive"

[retrieval]
lexical = true
semantic = false
# embedding_backend = "hash"  # hash | endpoint
# embedding_endpoint = ""
# embedding_model = ""
lex_weight = 0.7
sem_weight = 0.3

[answer]
mode = "local-first"
backend = "pi-cli"  # pi-cli | openai-compatible
pi_binary = "pi"
# pi_model = "provider/model-id"  # vazio usa o modelo global do Pi
# local_model_endpoint = "http://localhost:11434/v1"  # backend legado
# local_model = "local-model"
allow_extractive_fallback = true

[research]
enabled = false
require_confirmation = true
# Sem tecla em N segundos, pesquisa sozinho. 0 espera para sempre.
confirm_timeout = 5
# search_provider = "duckduckgo"
model_provider = "pi-cli"  # pi-cli | openai-compatible | claude-cli
pi_binary = "pi"
# claude-cli: Claude Code headless pesquisa sozinho (web, lore, Remnic).
# claude_model = "claude-opus-5-5"
# max_budget_usd = 2  # teto por pesquisa; 0 sem teto
# pi_model = "provider/model-id"  # vazio usa o modelo global do Pi
# model_endpoint = "http://localhost:11434/v1"  # backend legado
# model_name = "local-model"
# extra_patterns = []

[privacy]
redact_secrets = true
send_full_documents = false

[git]
# Commit automático dos paths que cada comando tocou + push oportunista.
# Nunca faz pull/rebase/force push; reconciliação fica no script lore-sync.
auto_commit = false
"""

GLOBAL_CONFIG_TEMPLATE = """\
# Acervo usado quando o comando roda fora de um repositório Lore.
repository:
  root: ""

# Modelo usado pelas chamadas não interativas de Lore ao Pi.
# Vazio usa o modelo padrão configurado no próprio Pi.
pi:
  binary: pi
  model: ""
"""


def global_config_path() -> str:
    config_home = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(config_home, "lore", "config.yaml")


def _load_global() -> tuple[dict, list[str]]:
    path = global_config_path()
    if not os.path.isfile(path):
        return {}, []
    try:
        with open(path, encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
    except (yaml.YAMLError, OSError) as exc:
        return {}, [f"config global inválida ({path}): {exc}"]
    if not isinstance(raw, dict):
        return {}, ["config global deve ser um mapa YAML"]
    return raw, []


def global_repository_root() -> str:
    """Raiz global do acervo, sem consultar configuração de projeto."""
    raw, errors = _load_global()
    if errors:
        return ""
    repository = raw.get("repository", {})
    if not isinstance(repository, dict):
        return ""
    root = repository.get("root", "")
    if not isinstance(root, str) or not root.strip():
        return ""
    return os.path.abspath(os.path.expanduser(root.strip()))


def _merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load(root: str) -> tuple[dict, list[str]]:
    """Merge defaults, YAML global e TOML do repo, nessa ordem de precedência."""
    config = _merge({}, DEFAULTS)
    errors: list[str] = []

    global_raw, global_errors = _load_global()
    errors.extend(global_errors)
    if not global_errors:
        config = _merge(config, global_raw)

    project_path = os.path.join(root, ".lore", "config.toml")
    if os.path.isfile(project_path):
        try:
            with open(project_path, "rb") as handle:
                project_raw = tomllib.load(handle)
            if not isinstance(project_raw, dict):
                errors.append("config do repo deve ser um mapa")
            else:
                project_repository = project_raw.get("repository")
                if isinstance(project_repository, dict) and "root" in project_repository:
                    project_raw = _merge({}, project_raw)
                    project_raw["repository"].pop("root", None)
                config = _merge(config, project_raw)
        except (tomllib.TOMLDecodeError, OSError) as exc:
            errors.append(f"config do repo inválida: {exc}")

    return config, errors


def init(root: str) -> str:
    """Cria .lore/config.toml. Erro se já existir."""
    path = os.path.join(root, ".lore", "config.toml")
    if os.path.exists(path):
        raise FileExistsError(f"config já existe: {path}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "x", encoding="utf-8") as handle:
        handle.write(CONFIG_TEMPLATE)
    return path


def init_global() -> str:
    """Cria config global YAML sem sobrescrever configuração existente."""
    path = global_config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "x", encoding="utf-8") as handle:
            handle.write(GLOBAL_CONFIG_TEMPLATE)
    except FileExistsError as exc:
        raise FileExistsError(f"config global já existe: {path}") from exc
    return path
