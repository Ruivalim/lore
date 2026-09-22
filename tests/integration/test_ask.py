"""Fase 3: ask extrativo, cobertura, stale, conflito, as-of, síntese local."""

import json
import os
import shutil
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from lore import index as index_mod
from lore import repo as repo_mod
from lore.answer import ask, validate_synthesis
from lore.cli import main


@pytest.fixture()
def repo(tmp_path):
    root = str(tmp_path / "repo")
    os.makedirs(os.path.join(root, "knowledge"))
    for name in os.listdir("tests/fixtures/corpus"):
        shutil.copy(
            os.path.join("tests/fixtures/corpus", name),
            os.path.join(root, "knowledge", name),
        )
    handle = repo_mod.Repo(root)
    index_mod.build(handle)
    return handle


def run_cli(root, *argv):
    return main(["--root", root, *argv])


def test_known_question_sufficient_with_citations(repo):
    answer = ask(repo, "como configurar split DNS no WireGuard")
    assert answer.coverage == "sufficient"
    assert len(answer.citations) >= 1
    for citation in answer.citations:
        path = citation.split("#")[0]
        assert os.path.isfile(path)
        assert "wireguard-split-dns" in path


def test_unknown_question_refused_without_invention(repo):
    answer = ask(repo, "como assar pão de fermentação natural em forno a lenha")
    assert answer.coverage == "insufficient"
    assert answer.citations == []
    assert "não contém" in answer.text
    assert "fermentação" not in answer.text


def test_partial_names_gap(repo):
    answer = ask(repo, "WireGuard openvpn")
    assert answer.coverage == "partial"
    assert "openvpn" in answer.gap
    assert answer.citations


def test_stale_warns(repo):
    answer = ask(repo, "instalar k3s com script")
    assert answer.coverage == "stale"
    assert "stale" in answer.text.lower()
    assert answer.citations


def test_conflicting_docs_shown(tmp_path):
    root = str(tmp_path / "repo")
    os.makedirs(os.path.join(root, "knowledge"))
    doc_a = (
        "---\nid: cafea\ntitle: Café e saúde\ntype: research\nstatus: verified\n"
        "tags:\n  - saude\n  - cafe\ncreated_at: 2026-01-01\nupdated_at: 2026-01-01\n"
        "verified_at: 2026-01-01\nsources:\n  - url: https://example.org/a\n"
        "    title: Estudo A\n    accessed_at: 2026-01-01\n---\n\n"
        "# Café e saúde\n\n## Evidências\n\nCafé moderado faz bem à saúde do coração.\n"
    )
    doc_b = (
        "---\nidd: placeholder\n".replace("idd", "id", 1).replace("placeholder", "cafeb")
        + "title: Café e coração\ntype: research\nstatus: verified\n"
        "tags:\n  - saude\n  - cafe\ncreated_at: 2026-01-01\nupdated_at: 2026-01-01\n"
        "verified_at: 2026-01-01\nsources:\n  - url: https://example.org/b\n"
        "    title: Estudo B\n    accessed_at: 2026-01-01\n---\n\n"
        "# Café e coração\n\n## Evidências\n\nCafé não é seguro para a saúde de cardíacos.\n"
    )
    with open(os.path.join(root, "knowledge", "a.md"), "w", encoding="utf-8") as handle:
        handle.write(doc_a)
    with open(os.path.join(root, "knowledge", "b.md"), "w", encoding="utf-8") as handle:
        handle.write(doc_b)
    handle_repo = repo_mod.Repo(root)
    index_mod.build(handle_repo)
    answer = ask(handle_repo, "café saúde coração")
    assert answer.coverage == "conflicting"
    assert "discordam" in answer.text


def test_as_of_excludes_newer(repo):
    answer = ask(repo, "split DNS WireGuard", as_of="2025-01-01")
    assert answer.coverage == "insufficient"


def test_yes_without_provider_errors(repo, capsys):
    assert run_cli(repo.root, "ask", "algo", "--yes") == 1
    assert "pesquisa" in capsys.readouterr().err


def test_ask_json(repo, capsys):
    assert run_cli(repo.root, "ask", "split DNS WireGuard", "--json") == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["coverage"] == "sufficient"
    assert payload["citations"]


def test_extractive_preserves_commands(repo):
    answer = ask(repo, "resolvectl status wg0")
    assert "resolvectl" in answer.text


def test_validate_synthesis_rejects_invented_file():
    citations = ["/x/knowledge/a.md#Seção"]
    assert validate_synthesis("Veja /x/knowledge/a.md#Seção.", citations) == []
    errors = validate_synthesis("Veja /x/outro.md.", citations)
    assert any("outro.md" in err for err in errors)
    assert validate_synthesis("Resposta sem fonte.", citations)


class _Handler(BaseHTTPRequestHandler):
    body = b"{}"

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        payload = json.dumps({
            "choices": [{"message": {"content": self.body.decode()}}]
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


@pytest.fixture()
def fake_llm():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()


def test_synthesis_used_when_valid(repo, tmp_path, fake_llm):
    citation = f"{repo.root}/knowledge/wireguard-split-dns.md#Procedimento"
    _Handler.body = f"Use DNS por domínio [{citation}].".encode()
    cfg = os.path.join(repo.root, ".lore", "config.toml")
    with open(cfg, "a", encoding="utf-8") as handle:
        handle.write(
            "\n[answer]\n"
            f'local_model_endpoint = "http://127.0.0.1:{fake_llm.server_port}"\n'
        )
    # Invalida índice? Não: config não entra no hash. Rebuild desnecessário.
    answer = ask(repo, "split DNS WireGuard", extractive=False)
    assert "Use DNS por domínio" in answer.text


def test_synthesis_falls_back_on_bad_citation(repo, fake_llm):
    _Handler.body = "Resposta sem fonte nenhuma.".encode()
    cfg = os.path.join(repo.root, ".lore", "config.toml")
    with open(cfg, "a", encoding="utf-8") as handle:
        handle.write(
            "\n[answer]\n"
            f'local_model_endpoint = "http://127.0.0.1:{fake_llm.server_port}"\n'
        )
    answer = ask(repo, "split DNS WireGuard", extractive=False)
    assert "Fontes locais:" in answer.text
    assert "extrativo" in answer.text


def test_synthesis_falls_back_when_endpoint_down(repo):
    cfg = os.path.join(repo.root, ".lore", "config.toml")
    with open(cfg, "a", encoding="utf-8") as handle:
        handle.write('\n[answer]\nlocal_model_endpoint = "http://127.0.0.1:1"\n')
    answer = ask(repo, "split DNS WireGuard", extractive=False)
    assert "Fontes locais:" in answer.text
