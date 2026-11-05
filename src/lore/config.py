"""Configuração global YAML e configuração por repositório TOML."""

from __future__ import annotations

import os
import tomllib

import yaml

EXAMPLE_PATH = os.path.join(os.path.dirname(__file__), "config.example.toml")

with open(EXAMPLE_PATH, encoding="utf-8") as _handle:
    CONFIG_TEMPLATE = _handle.read()

# O exemplo é a fonte dos defaults: opção nova entra lá, não aqui.
DEFAULTS: dict = tomllib.loads(CONFIG_TEMPLATE)

LLM_TASKS = ("answer", "import", "research")
LLM_TASK_KEYS = ("agent", "model")

GLOBAL_CONFIG_TEMPLATE = """\
# Acervo usado quando o comando roda fora de um repositório Lore.
repository:
  root: ""

# Agente de linguagem padrão; todas as opções em config.example.toml.
llm:
  agent: pi
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


def unknown_keys(raw: dict, origin: str) -> list[str]:
    """Chaves que o Lore não lê. Vira aviso no doctor, nunca erro."""
    found: list[str] = []
    for section, values in raw.items():
        if section == "agents":
            if not isinstance(values, dict):
                found.append(f"{origin}: [agents] deve ser uma tabela")
                continue
            from .agents import FIELDS

            for name, spec in values.items():
                if not isinstance(spec, dict):
                    found.append(f"{origin}: [agents.{name}] deve ser uma tabela")
                    continue
                found.extend(f"{origin}: agents.{name}.{key}"
                             for key in spec if key not in FIELDS)
            continue
        if section not in DEFAULTS:
            found.append(f"{origin}: [{section}]")
            continue
        if not isinstance(values, dict):
            found.append(f"{origin}: {section} deve ser uma tabela")
            continue
        for key, value in values.items():
            if section == "llm" and key in LLM_TASKS:
                if not isinstance(value, dict):
                    found.append(f"{origin}: llm.{key} deve ser uma tabela")
                    continue
                found.extend(f"{origin}: llm.{key}.{sub}"
                             for sub in value if sub not in LLM_TASK_KEYS)
                continue
            if key not in DEFAULTS[section]:
                found.append(f"{origin}: {section}.{key}")
    return found


def config_warnings(root: str) -> list[str]:
    """Chaves desconhecidas no YAML global e no TOML do acervo."""
    warnings: list[str] = []
    global_raw, errors = _load_global()
    if not errors:
        warnings.extend(unknown_keys(global_raw, "config global"))
    project_path = os.path.join(root, ".lore", "config.toml")
    if os.path.isfile(project_path):
        try:
            with open(project_path, "rb") as handle:
                project_raw = tomllib.load(handle)
        except (tomllib.TOMLDecodeError, OSError):
            project_raw = {}
        warnings.extend(unknown_keys(project_raw, ".lore/config.toml"))
    return warnings


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
