import subprocess

import pytest

from lore import pi_cli


def test_complete_invokes_pi_ephemerally_without_tools(monkeypatch):
    observed = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed.update(kwargs)
        return subprocess.CompletedProcess(command, 0, stdout=" resposta \n", stderr="")

    monkeypatch.setattr(pi_cli.subprocess, "run", fake_run)
    result = pi_cli.complete("prompt com dado privado", model="openai/example")

    command = observed["command"]
    assert result == "resposta"
    assert observed["input"] == "prompt com dado privado"
    assert "prompt com dado privado" not in command
    assert "--no-session" in command
    assert "--no-tools" in command
    assert "--no-extensions" in command
    assert "--no-context-files" in command
    assert command[command.index("--model") + 1] == "openai/example"


def test_complete_reports_cli_failure(monkeypatch):
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 2, stdout="", stderr="auth missing")

    monkeypatch.setattr(pi_cli.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="auth missing"):
        pi_cli.complete("prompt")


def test_complete_reports_timeout(monkeypatch):
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(pi_cli.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="tempo limite"):
        pi_cli.complete("prompt")
