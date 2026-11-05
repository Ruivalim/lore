"""Adapter do `claude -p`: comando, leitura do JSON e processo real (binário falso)."""

import json
import os

import pytest

from lore import claude_cli
from lore.claude_cli import build_command, parse_output


def _ok(**structured):
    return json.dumps({
        "type": "result", "subtype": "success", "is_error": False,
        "total_cost_usd": 0.42, "permission_denials": [],
        "structured_output": structured,
    })


def test_command_blocks_writes_and_personal_connectors():
    cmd = build_command("claude", "", 0)
    denied = cmd[cmd.index("--disallowed-tools") + 1:]
    for tool in ("Edit", "Write", "NotebookEdit", "mcp__claude_ai_Gmail",
                 "mcp__claude_ai_Google_Drive", "mcp__claude_ai_Google_Calendar"):
        assert tool in denied
    assert cmd[cmd.index("--model") + 1] == "claude-opus-5-5"
    assert cmd[cmd.index("--permission-mode") + 1] == "auto"
    assert "--no-session-persistence" in cmd
    assert "--max-budget-usd" not in cmd
    schema = json.loads(cmd[cmd.index("--json-schema") + 1])
    assert schema["required"] == ["summary", "answer", "sources"]


def test_command_budget_and_model_override():
    cmd = build_command("/x/claude", "claude-sonnet-5-5", 1.5)
    assert cmd[0] == "/x/claude"
    assert cmd[cmd.index("--model") + 1] == "claude-sonnet-5-5"
    assert cmd[cmd.index("--max-budget-usd") + 1] == "1.5"


def test_disallowed_tools_is_last_variadic():
    # --disallowed-tools engole o que vier depois; tem que fechar o comando.
    cmd = build_command("claude", "", 2)
    assert cmd[-len(claude_cli.DENIED_TOOLS) - 1:] == [
        "--disallowed-tools", *claude_cli.DENIED_TOOLS]


def test_parse_success_filters_sources():
    out = parse_output(_ok(answer="  ## Resposta\nx  ", sources=[
        {"url": "https://a.dev/doc", "title": "A"},
        {"url": "https://a.dev/doc", "title": "A de novo"},
        {"url": "file:///etc/passwd", "title": "local"},
        {"url": "javascript:alert(1)", "title": "js"},
        {"url": "http://b.dev", "title": ""},
        "lixo",
    ]))
    assert out.answer == "## Resposta\nx"
    assert out.sources == [{"url": "https://a.dev/doc", "title": "A"},
                           {"url": "http://b.dev", "title": "http://b.dev"}]
    assert out.cost_usd == 0.42


def test_parse_reports_denied_tools():
    data = json.loads(_ok(answer="x", sources=[]))
    data["permission_denials"] = [{"tool_name": "Write", "tool_input": {}}]
    assert parse_output(json.dumps(data)).denied == ["Write"]


@pytest.mark.parametrize("stdout, message", [
    ("", "não é JSON"),
    ("Error: not logged in", "não é JSON"),
    ("[]", "formato inesperado"),
    (json.dumps({"subtype": "error_max_budget_usd", "is_error": True}), "error_max_budget_usd"),
    (json.dumps({"subtype": "success", "is_error": True, "result": "API down"}), "API down"),
    (json.dumps({"subtype": "success", "is_error": False}), "formato pedido"),
    (_ok(answer="   ", sources=[]), "vazia"),
])
def test_parse_failures_explain(stdout, message):
    with pytest.raises(RuntimeError, match=message):
        parse_output(stdout)


def _fake_claude(tmp_path, body):
    path = tmp_path / "claude"
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)
    return str(path)


def test_research_runs_process_with_stdin_and_cwd(tmp_path):
    log = tmp_path / "log"
    workdir = tmp_path / "repo"
    workdir.mkdir()
    payload = _ok(answer="resposta", sources=[]).replace("'", "")
    binary = _fake_claude(tmp_path, (
        f'pwd > {log}; cat >> {log}; echo "--ARGS--" >> {log}; '
        f'printf "%s\\n" "$@" >> {log}\n'
        f"echo '{payload}'\n"))
    result = claude_cli.research("Qual a porta?", "[fonte local: x]\ntrecho",
                                 binary=binary, cwd=str(workdir))
    assert result.answer == "resposta"
    text = log.read_text()
    assert text.splitlines()[0] == str(workdir)
    assert "Pergunta: Qual a porta?" in text and "trecho" in text
    # a pergunta vai por stdin, nunca por argv (não aparece em `ps`)
    assert "Qual a porta?" not in text.split("--ARGS--")[1]


def test_research_nonzero_without_output(tmp_path):
    binary = _fake_claude(tmp_path, "echo 'boom no stderr' >&2; exit 3\n")
    with pytest.raises(RuntimeError, match="boom no stderr"):
        claude_cli.research("q", binary=binary)


def test_research_nonzero_with_error_json(tmp_path):
    payload = json.dumps({"subtype": "error_during_execution", "is_error": True})
    binary = _fake_claude(tmp_path, f"echo '{payload}'; exit 1\n")
    with pytest.raises(RuntimeError, match="error_during_execution"):
        claude_cli.research("q", binary=binary)


def test_research_timeout(tmp_path):
    binary = _fake_claude(tmp_path, "exec sleep 30\n")
    with pytest.raises(RuntimeError, match="tempo limite"):
        claude_cli.research("q", binary=binary, timeout=1)


def test_research_missing_binary():
    with pytest.raises(RuntimeError, match="não foi possível executar"):
        claude_cli.research("q", binary=os.path.join("/nao", "existe", "claude"))
