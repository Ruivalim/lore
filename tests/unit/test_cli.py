"""CLI Fase 1: new, add, show, doctor, config."""

import json
import os
import subprocess
import sys


from lore.cli import main


def run_cli(repo_root, *argv):
    return main(["--root", repo_root, *argv])


def test_new_creates_valid_draft(empty_repo, capsys):
    assert run_cli(empty_repo, "new", "--type", "howto", "--title", "Meu Guia") == 0
    out = capsys.readouterr().out
    assert "meu-guia" in out
    path = os.path.join(empty_repo, "drafts", "meu-guia.md")
    assert os.path.isfile(path)
    with open(path, encoding="utf-8") as handle:
        from lore.models import parse_doc

        assert parse_doc(handle.read(), path).valid


def test_new_every_type(empty_repo, capsys):
    from lore.models import TYPES

    for doc_type in TYPES:
        title = f"Doc {doc_type}"
        assert run_cli(empty_repo, "new", "--type", doc_type, "--title", title) == 0
        capsys.readouterr()
    assert len(os.listdir(os.path.join(empty_repo, "drafts"))) == len(TYPES)


def test_new_duplicate_file_fails(empty_repo, capsys):
    assert run_cli(empty_repo, "new", "--type", "note", "--title", "Repete") == 0
    capsys.readouterr()
    assert run_cli(empty_repo, "new", "--type", "note", "--title", "Repete") == 1


def test_add_and_show(lore_repo, tmp_path, capsys):
    from tests.conftest import VALID_NOTE

    src = tmp_path / "extra.md"
    src.write_text(VALID_NOTE.replace("ideia-backup", "extra-doc"), encoding="utf-8")
    assert run_cli(lore_repo, "add", str(src), "--to", "knowledge") == 0
    capsys.readouterr()
    assert run_cli(lore_repo, "show", "extra-doc") == 0
    assert "Ideia de backup" in capsys.readouterr().out


def test_show_missing(lore_repo, capsys):
    assert run_cli(lore_repo, "show", "nao-existe") == 1


def test_doctor_flags_invalid(lore_repo, capsys):
    assert run_cli(lore_repo, "doctor") == 1
    out = capsys.readouterr().out
    assert "sem-id.md" in out


def test_doctor_clean(empty_repo, capsys):
    assert run_cli(empty_repo, "doctor") == 0
    assert "ok" in capsys.readouterr().out


def test_doctor_json(lore_repo, capsys):
    assert run_cli(lore_repo, "doctor", "--json") == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert any("sem-id.md" in item for item in payload["problems"])


def test_config_init_and_show(tmp_path, capsys):
    root = str(tmp_path / "repo")
    os.makedirs(os.path.join(root, "knowledge"))
    assert run_cli(root, "config", "--init") == 0
    capsys.readouterr()
    assert os.path.isfile(os.path.join(root, ".lore", "config.toml"))
    assert run_cli(root, "config", "--init") == 1  # já existe
    capsys.readouterr()
    assert run_cli(root, "config", "--json") == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["config"]["git"]["auto_commit"] is False
    assert "auto_commit" not in payload["config"]["privacy"]


def test_main_uses_global_repository_outside_tree(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "library"
    (repo / "knowledge").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    config_home = tmp_path / "config"
    global_path = config_home / "lore" / "config.yaml"
    global_path.parent.mkdir(parents=True)
    global_path.write_text(f'repository:\n  root: "{repo}"\n', encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.chdir(outside)

    assert main(["doctor"]) == 0
    assert "ok" in capsys.readouterr().out


def test_main_reports_missing_repository(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.chdir(tmp_path)

    assert main(["doctor"]) == 1
    assert "nenhum repositório Lore" in capsys.readouterr().err


def test_installed_binary_runs():
    binary = os.path.join(sys.prefix, "bin", "lore")
    assert os.path.isfile(binary), f"binário lore ausente em {binary}"
    proc = subprocess.run(
        [binary, "--help"], capture_output=True, text=True
    )
    assert proc.returncode == 0
    assert "usage" in proc.stdout
