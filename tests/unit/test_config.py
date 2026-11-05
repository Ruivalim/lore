import os

import pytest

from lore import config


def test_global_repository_root_expands_user(tmp_path, monkeypatch):
    config_home = tmp_path / "config"
    global_path = config_home / "lore" / "config.yaml"
    global_path.parent.mkdir(parents=True)
    global_path.write_text('repository:\n  root: "~/lore-library"\n', encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    assert config.global_repository_root() == str(tmp_path / "home" / "lore-library")


def test_project_toml_cannot_override_global_repository_root(tmp_path, monkeypatch):
    config_home = tmp_path / "config"
    global_path = config_home / "lore" / "config.yaml"
    global_path.parent.mkdir(parents=True)
    global_path.write_text(
        f'repository:\n  root: "{tmp_path / "global-repo"}"\n', encoding="utf-8"
    )
    repo = tmp_path / "repo"
    (repo / ".lore").mkdir(parents=True)
    (repo / ".lore" / "config.toml").write_text(
        f'[repository]\nroot = "{tmp_path / "wrong-repo"}"\n', encoding="utf-8"
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))

    loaded, errors = config.load(str(repo))

    assert errors == []
    assert loaded["repository"]["root"] == str(tmp_path / "global-repo")


def test_global_yaml_loaded_and_project_toml_overrides(tmp_path, monkeypatch):
    config_home = tmp_path / "config"
    global_path = config_home / "lore" / "config.yaml"
    global_path.parent.mkdir(parents=True)
    global_path.write_text(
        "pi:\n  binary: pi-global\n  model: provider/global-model\n",
        encoding="utf-8",
    )
    repo = tmp_path / "repo"
    (repo / ".lore").mkdir(parents=True)
    (repo / ".lore" / "config.toml").write_text(
        '[pi]\nmodel = "provider/project-model"\n', encoding="utf-8"
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))

    loaded, errors = config.load(str(repo))

    assert errors == []
    assert loaded["pi"] == {"binary": "pi-global", "model": "provider/project-model"}


def test_global_config_init_does_not_overwrite(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    path = config.init_global()
    assert os.path.isfile(path)
    with pytest.raises(FileExistsError, match="já existe"):
        config.init_global()


def test_cli_initializes_global_config(tmp_path, monkeypatch, capsys):
    from lore.cli import main

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    assert main(["--root", str(tmp_path), "config", "--global", "--init"]) == 0
    result = capsys.readouterr().out
    assert "config.yaml" in result
    assert (tmp_path / "cfg" / "lore" / "config.yaml").is_file()


def test_invalid_global_yaml_reports_error(tmp_path, monkeypatch):
    config_home = tmp_path / "config"
    path = config_home / "lore" / "config.yaml"
    path.parent.mkdir(parents=True)
    path.write_text("pi: [unfinished", encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))

    _, errors = config.load(str(tmp_path / "repo"))

    assert errors and "config global inválida" in errors[0]


def test_example_is_the_defaults_and_init_template(tmp_path):
    import tomllib

    with open(config.EXAMPLE_PATH, "rb") as handle:
        example = tomllib.load(handle)
    assert example == config.DEFAULTS
    path = config.init(str(tmp_path))
    with open(path, encoding="utf-8") as handle:
        assert handle.read() == config.CONFIG_TEMPLATE


def test_example_has_no_unknown_keys():
    assert config.unknown_keys(config.DEFAULTS, "exemplo") == []


def test_every_key_read_by_code_is_in_example():
    """Chave lida no código e ausente do exemplo é opção escondida."""
    import re
    from pathlib import Path

    src = Path(config.__file__).parent
    read = set()
    for path in src.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for section, key in re.findall(
                r'cfg\.get\("(\w+)", \{\}\)\.get\("(\w+)"', text):
            read.add((section, key))
    missing = {(s, k) for s, k in read if k not in config.DEFAULTS.get(s, {})}
    assert not missing


def test_unknown_keys_cover_sections_tasks_and_agents():
    raw = {
        "answer": {"backend": "pi-cli"},
        "llm": {"agent": "pi", "modelo": "x", "answer": {"agent": "codex", "temp": 1},
                "research": "claude"},
        "agents": {"meu": {"command": ["x"], "comand": ["y"]}, "ruim": "x"},
        "git": {"auto_commit": True},
        "research": {"model_provider": "pi-cli"},
    }
    found = config.unknown_keys(raw, "t")
    assert "t: [answer]" in found
    assert "t: llm.modelo" in found
    assert "t: llm.answer.temp" in found
    assert "t: llm.research deve ser uma tabela" in found
    assert "t: agents.meu.comand" in found
    assert "t: [agents.ruim] deve ser uma tabela" in found
    assert "t: research.model_provider" in found
    assert not any("auto_commit" in item for item in found)


def test_doctor_warns_about_legacy_keys(lore_repo, tmp_path, monkeypatch, capsys):
    import json

    from lore.cli import main

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    with open(os.path.join(lore_repo, ".lore", "config.toml"), "a", encoding="utf-8") as h:
        h.write('[pi]\nmodel = "x"\n')
    main(["--root", lore_repo, "doctor", "--json"])
    warnings = json.loads(capsys.readouterr().out)["warnings"]
    assert any("chave desconhecida, ignorada: .lore/config.toml: [pi]" in w for w in warnings)


def test_doctor_probe_reports_agent_that_answers_with_error(lore_repo, tmp_path,
                                                            monkeypatch, capsys):
    import json
    import sys

    from lore.cli import main

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    script = tmp_path / "cli.py"
    script.write_text("print('No API key found')", encoding="utf-8")
    with open(os.path.join(lore_repo, ".lore", "config.toml"), "a", encoding="utf-8") as h:
        h.write(f'[llm]\nagent = "falso"\n[agents.falso]\n'
                f'command = ["{sys.executable}", "{script}"]\n'
                'error_patterns = ["^No API key"]\n')
    main(["--root", lore_repo, "doctor", "--json"])
    without_probe = json.loads(capsys.readouterr().out)["problems"]
    assert not any("não respondeu" in p for p in without_probe)  # sem chamada
    assert main(["--root", lore_repo, "doctor", "--probe", "--json"]) == 1
    problems = json.loads(capsys.readouterr().out)["problems"]
    assert any("llm.answer: falso não respondeu" in p for p in problems)


def test_doctor_warns_missing_agent_binary(lore_repo, tmp_path, monkeypatch, capsys):
    import json

    from lore.cli import main

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    with open(os.path.join(lore_repo, ".lore", "config.toml"), "a", encoding="utf-8") as h:
        h.write('[agents.pi]\nbinary = "/nao/existe/pi"\n')
    main(["--root", lore_repo, "doctor", "--json"])
    warnings = json.loads(capsys.readouterr().out)["warnings"]
    assert any("binário de pi não encontrado" in w for w in warnings)
