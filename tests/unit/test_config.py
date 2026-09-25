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
