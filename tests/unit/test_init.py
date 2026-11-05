"""lore init: cria acervo sem sobrescrever nada e sem aninhar repositório Git."""

import json
import os
import shutil
import subprocess

import pytest

from lore import repo as repo_mod
from lore.cli import main

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git ausente")


@pytest.fixture(autouse=True)
def isolated_global_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))


@needs_git
def test_init_creates_layout_config_gitignore_and_git(tmp_path, capsys):
    target = tmp_path / "acervo"
    assert main(["init", str(target), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["ok"] and payload["git_initialized"]
    for name in repo_mod.MANAGED_DIRS:
        assert (target / name / ".gitkeep").is_file()
    assert (target / ".lore" / "config.toml").is_file()
    assert ".lore/" in (target / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert (target / ".git").is_dir()
    assert repo_mod.is_repo_root(str(target))


def test_init_result_is_usable_by_other_commands(tmp_path, capsys):
    target = tmp_path / "acervo"
    assert main(["init", str(target), "--no-git"]) == 0
    capsys.readouterr()
    assert main(["--root", str(target), "new", "--type", "note", "--title", "Primeira"]) == 0
    assert (target / "drafts" / "primeira.md").is_file()
    assert main(["--root", str(target), "doctor"]) == 0


def test_init_refuses_existing_lore_repo(lore_repo, capsys):
    config = os.path.join(lore_repo, ".lore", "config.toml")
    before = open(config, encoding="utf-8").read()
    assert main(["init", lore_repo, "--no-git"]) == 1
    assert "já é um repositório Lore" in capsys.readouterr().err
    assert open(config, encoding="utf-8").read() == before


def test_init_refuses_file_path(tmp_path, capsys):
    target = tmp_path / "arquivo"
    target.write_text("x", encoding="utf-8")
    assert main(["init", str(target), "--no-git"]) == 1
    assert "não é um diretório" in capsys.readouterr().err
    assert target.read_text(encoding="utf-8") == "x"


def test_init_keeps_existing_gitignore_and_files(tmp_path, capsys):
    target = tmp_path / "acervo"
    target.mkdir()
    (target / ".gitignore").write_text("segredo.txt", encoding="utf-8")
    (target / "LEIAME.md").write_text("meu", encoding="utf-8")

    assert main(["init", str(target), "--no-git"]) == 0
    capsys.readouterr()
    lines = (target / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "segredo.txt"
    assert ".lore/" in lines
    assert (target / "LEIAME.md").read_text(encoding="utf-8") == "meu"


def test_init_does_not_duplicate_gitignore_line(tmp_path, capsys):
    target = tmp_path / "acervo"
    target.mkdir()
    (target / ".gitignore").write_text(".lore/\n", encoding="utf-8")
    assert main(["init", str(target), "--no-git"]) == 0
    capsys.readouterr()
    assert (target / ".gitignore").read_text(encoding="utf-8") == ".lore/\n"


@needs_git
def test_init_inside_existing_git_repo_does_not_nest(tmp_path, capsys):
    outer = tmp_path / "outer"
    outer.mkdir()
    subprocess.run(["git", "init", "-q", str(outer)], check=True)
    target = outer / "acervo"

    assert main(["init", str(target), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["git_initialized"] is False
    assert not (target / ".git").exists()


def test_init_no_git_flag(tmp_path, capsys):
    target = tmp_path / "acervo"
    assert main(["init", str(target), "--no-git"]) == 0
    assert not (target / ".git").exists()
    assert "repository.root" in capsys.readouterr().out
