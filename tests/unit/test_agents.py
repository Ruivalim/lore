"""Agentes de texto: presets, CLI genérico, seleção por tarefa e falhas.

O que quebra de verdade: CLI que sai 0 com erro, prompt maior que o limite de
argumento, modelo herdado pelo agente errado, CLI rodando dentro do acervo.
Os testes de execução usam um CLI falso real (script Python), não mock.
"""

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from lore import agents
from lore.agents import Agent, AgentError, definition, resolve, selection

FAKE_CLI = r'''
import json, os, sys, time
mode = sys.argv[1]
args = sys.argv[2:]
stdin = sys.stdin.read() if not sys.stdin.isatty() else ""
if mode == "echo":
    print(json.dumps({"args": args, "stdin": stdin, "cwd": os.getcwd()}))
elif mode == "rc0-error":
    print("No API key found for provider x")
elif mode == "fail":
    print("detalhe do erro", file=sys.stderr); sys.exit(3)
elif mode == "empty":
    pass
elif mode == "sleep":
    time.sleep(5)
elif mode == "outfile":
    path = args[args.index("-o") + 1]
    open(path, "w").write("resposta no arquivo")
    print("ruído de progresso")
'''


@pytest.fixture()
def fake_cli(tmp_path):
    script = tmp_path / "fake_cli.py"
    script.write_text(FAKE_CLI, encoding="utf-8")
    return [sys.executable, str(script)]


def _agent(fake_cli, mode, **kw):
    return Agent(name="fake", command=[*fake_cli, mode, *kw.pop("extra", [])], **kw)


# --- montagem de comando por preset -------------------------------------------

def _preset(name, model=""):
    cfg = {"llm": {"agent": name, "model": model}}
    return resolve(cfg, "answer")


def test_pi_preset_without_model_has_no_model_flag():
    command = _preset("pi").build_command("p", "SYS", "/x")
    assert command[0] == "pi" and "--no-tools" in command
    assert "--model" not in command
    assert command[command.index("--system-prompt") + 1] == "SYS"


def test_pi_preset_with_model():
    command = _preset("pi", "deepseek/v4").build_command("p", "SYS", "/x")
    assert command[-2:] == ["--model", "deepseek/v4"]


def test_claude_preset_disables_tools_and_settings():
    command = _preset("claude", "claude-haiku-5-5").build_command("p", "SYS", "/x")
    assert command[command.index("--tools") + 1] == ""
    assert command[command.index("--setting-sources") + 1] == ""
    assert "--strict-mcp-config" in command
    assert command[-2:] == ["--model", "claude-haiku-5-5"]


def test_codex_preset_reads_stdin_after_model_and_writes_output_file():
    command = _preset("codex", "gpt-x").build_command("p", "SYS", "/tmp/out.txt")
    assert command[-1] == "-"
    assert command[command.index("--output-last-message") + 1] == "/tmp/out.txt"
    assert command.index("--model") < command.index("-")
    assert command[command.index("--sandbox") + 1] == "read-only"


def test_agy_preset_puts_model_before_glued_prompt_with_system():
    agent = _preset("agy", "gemini-3.8-flash-low")
    command = agent.build_command("pergunta", "SYS", "/x")
    assert command[1:3] == ["--model", "gemini-3.8-flash-low"]
    assert command[-1] == "-p=SYS\n\npergunta"
    assert agent.stdin_for("pergunta", "SYS") is None


def test_agy_rejects_prompt_over_arg_limit():
    agent = _preset("agy")
    with pytest.raises(AgentError, match="grande demais"):
        agent.build_command("x" * 131_072, "", "/x")
    agent.build_command("x" * 130_000, "", "/x")


def test_braces_in_prompt_are_not_placeholders():
    agent = _preset("agy")
    command = agent.build_command("dict {model} e {nada}", "", "/x")
    assert command[-1] == "-p=dict {model} e {nada}"


# --- execução real ------------------------------------------------------------

def test_stdin_agent_gets_system_prepended_when_command_has_no_system(fake_cli):
    out = json.loads(_agent(fake_cli, "echo").complete("pergunta", system="SYS"))
    assert out["stdin"] == "SYS\n\npergunta"


def test_agent_runs_in_empty_temp_dir_not_cwd(fake_cli, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = json.loads(_agent(fake_cli, "echo").complete("p"))
    assert out["cwd"] != str(tmp_path)
    assert os.path.basename(out["cwd"]).startswith("lore-agent-")
    assert not os.path.exists(out["cwd"])  # limpo depois


def test_rc0_with_error_text_is_failure(fake_cli):
    agent = _agent(fake_cli, "rc0-error", error_patterns=agents.PRESETS["pi"]["error_patterns"])
    with pytest.raises(AgentError, match="devolveu erro"):
        agent.complete("p")


def test_nonzero_exit_reports_stderr(fake_cli):
    with pytest.raises(AgentError, match="detalhe do erro"):
        _agent(fake_cli, "fail").complete("p")


def test_empty_output_is_failure(fake_cli):
    with pytest.raises(AgentError, match="vazia"):
        _agent(fake_cli, "empty").complete("p")


def test_timeout_is_agent_error(fake_cli):
    with pytest.raises(AgentError, match="tempo limite"):
        _agent(fake_cli, "sleep", timeout=1).complete("p")


def test_missing_binary_is_agent_error():
    agent = Agent(name="x", command=["/nao/existe/cli"])
    with pytest.raises(AgentError, match="não foi possível executar"):
        agent.complete("p")


def test_output_file_wins_over_stdout(fake_cli):
    agent = _agent(fake_cli, "outfile", extra=["-o", "{output_file}"])
    assert agent.complete("p") == "resposta no arquivo"


def test_arg_mode_appends_prompt_when_no_placeholder(fake_cli):
    agent = _agent(fake_cli, "echo", prompt="arg")
    out = json.loads(agent.complete("pergunta", system=""))
    assert out["args"][-1] == "pergunta" and out["stdin"] == ""


# --- seleção e definição ------------------------------------------------------

def test_selection_defaults_to_pi():
    assert selection({}, "answer") == ("pi", "")


def test_task_inherits_model_only_from_same_agent():
    cfg = {"llm": {"agent": "pi", "model": "deepseek/v4",
                   "research": {"agent": "claude"}, "import": {"agent": "pi"}}}
    assert selection(cfg, "answer") == ("pi", "deepseek/v4")
    assert selection(cfg, "import") == ("pi", "deepseek/v4")
    assert selection(cfg, "research") == ("claude", "")


def test_task_explicit_empty_model_overrides_inheritance():
    cfg = {"llm": {"agent": "pi", "model": "x/y", "answer": {"model": ""}}}
    assert selection(cfg, "answer") == ("pi", "")


def test_unknown_task_raises():
    with pytest.raises(ValueError):
        selection({}, "resumo")


def test_unknown_agent_lists_known():
    with pytest.raises(ValueError, match="agente desconhecido: nada.*codex"):
        definition({}, "nada")


def test_override_merges_with_preset():
    spec = definition({"agents": {"pi": {"binary": "/opt/pi", "timeout": 9}}}, "pi")
    assert spec["binary"] == "/opt/pi" and spec["timeout"] == 9
    assert "--no-tools" in spec["command"]


@pytest.mark.parametrize("override, message", [
    ({"comand": ["x"]}, "chave desconhecida: comand"),
    ({"command": "x --y"}, "lista de strings"),
    ({"command": ["x"], "prompt": "file"}, "stdin ou arg"),
    ({"kind": "grpc"}, "cli ou openai"),
])
def test_bad_custom_definitions(override, message):
    with pytest.raises(ValueError, match=message):
        definition({"agents": {"meu": override}}, "meu")


def test_custom_cli_agent_end_to_end(fake_cli):
    cfg = {"llm": {"agent": "meu", "model": "m1"},
           "agents": {"meu": {"command": [*fake_cli, "echo", "{model_args}"],
                              "model_args": ["--model", "{model}"]}}}
    out = json.loads(resolve(cfg, "answer").complete("p", system=""))
    assert out["args"] == ["--model", "m1"]


# --- endpoint OpenAI-compatível -----------------------------------------------

class _Chat(BaseHTTPRequestHandler):
    seen = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Chat.seen.append((self.path, self.headers.get("Authorization"), body))
        data = json.dumps({"choices": [{"message": {"content": "olá"}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        pass


def test_openai_agent_sends_system_model_and_key(monkeypatch):
    server = HTTPServer(("127.0.0.1", 0), _Chat)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("MINHA_CHAVE", "segredo")
    try:
        cfg = {"llm": {"agent": "local", "model": "qwen"},
               "agents": {"local": {"kind": "openai", "api_key_env": "MINHA_CHAVE",
                                    "endpoint": f"http://127.0.0.1:{server.server_port}/v1"}}}
        assert resolve(cfg, "answer").complete("p", system="SYS") == "olá"
    finally:
        server.shutdown()
    path, auth, body = _Chat.seen[-1]
    assert path == "/v1/chat/completions" and auth == "Bearer segredo"
    assert body["model"] == "qwen"
    assert body["messages"][0] == {"role": "system", "content": "SYS"}


def test_openai_agent_connection_refused_is_agent_error():
    agent = Agent(name="local", kind="openai", endpoint="http://127.0.0.1:1", timeout=2)
    with pytest.raises(AgentError, match="local falhou"):
        agent.complete("p")


def test_openai_agent_without_endpoint():
    with pytest.raises(AgentError, match="sem `endpoint`"):
        Agent(name="openai", kind="openai").complete("p")


def test_executable_is_binary_for_presets_and_first_word_for_custom():
    assert _preset("pi").executable() == "pi"
    spec = {"llm": {"agent": "meu"}, "agents": {"meu": {"command": ["/usr/bin/env", "x"]}}}
    assert resolve(spec, "answer").executable() == "/usr/bin/env"
    override = {"agents": {"codex": {"binary": "/opt/codex"}}, "llm": {"agent": "codex"}}
    assert resolve(override, "answer").executable() == "/opt/codex"
