import json
import os
from pathlib import Path

import pytest

from lore import repo as repo_mod
from lore.importer import import_markdown
from lore.models import parse_doc


@pytest.fixture
def repo(tmp_path):
    root = str(tmp_path / "lore")
    for directory in ("knowledge", "drafts", "archive"):
        os.makedirs(os.path.join(root, directory))
    return repo_mod.Repo(root)


def test_import_uses_pi_metadata_and_preserves_body(repo, tmp_path, monkeypatch):
    source = tmp_path / "source.md"
    original = "# Split DNS\n\nUse `resolvectl dns wg0 10.0.0.53`.\n"
    source.write_text(original, encoding="utf-8")
    calls = []

    def fake_complete(prompt, *, binary, model):
        calls.append((prompt, binary, model))
        return json.dumps(
            {
                "title": "Split DNS com WireGuard",
                "type": "howto",
                "tags": ["WireGuard", "DNS local"],
            }
        )

    monkeypatch.setattr("lore.importer.complete", fake_complete)
    result = import_markdown(
        repo,
        str(source),
        {
            "pi": {"binary": "/usr/bin/pi", "model": "deepseek/example"},
            "privacy": {"extra_patterns": []},
        },
    )

    imported = parse_doc(Path(result.path).read_text(encoding="utf-8"), result.path)
    assert imported.valid
    assert imported.front["status"] == "draft"
    assert imported.front["type"] == "howto"
    assert imported.front["tags"] == ["wireguard", "dns-local"]
    assert imported.front["sources"][0]["kind"] == "local"
    assert imported.body.lstrip("\n") == original
    assert source.read_text(encoding="utf-8") == original
    assert calls and "Markdown para classificar" in calls[0][0]
    assert calls[0][1:] == ("/usr/bin/pi", "deepseek/example")


def test_import_blocks_secret_before_pi(repo, tmp_path, monkeypatch):
    source = tmp_path / "secret.md"
    source.write_text("# Key\n\nToken: ghp_abcdefghij12345678901234567890\n")
    monkeypatch.setattr(
        "lore.importer.complete",
        lambda *a, **k: pytest.fail("Pi must not receive detected secrets"),
    )
    with pytest.raises(ValueError, match="bloqueada"):
        import_markdown(repo, str(source), {"privacy": {}})
    assert os.listdir(repo.managed_dir(repo_mod.DRAFTS)) == []


def test_import_rejects_bad_pi_metadata_without_writing(repo, tmp_path, monkeypatch):
    source = tmp_path / "note.md"
    source.write_text("# A note\n\nBody.\n")
    monkeypatch.setattr("lore.importer.complete", lambda *a, **k: "not json")
    with pytest.raises(ValueError, match="JSON"):
        import_markdown(repo, str(source), {})
    assert os.listdir(repo.managed_dir(repo_mod.DRAFTS)) == []


def test_cli_import_emits_json_draft(repo, tmp_path, monkeypatch, capsys):
    from lore.cli import main

    source = tmp_path / "cli.md"
    source.write_text("# CLI import\n\nConteúdo.\n", encoding="utf-8")
    monkeypatch.setattr(
        "lore.importer.complete",
        lambda *a, **k: '{"title":"CLI import","type":"note","tags":["cli"]}',
    )

    assert main(["--root", repo.root, "import", str(source), "--json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "draft"
    assert output["id"] == "cli-import"


def test_import_suffixes_duplicate_ids(repo, tmp_path, monkeypatch):
    source = tmp_path / "one.md"
    source.write_text("# A note\n\nBody.\n")
    monkeypatch.setattr(
        "lore.importer.complete",
        lambda *a, **k: '{"title":"Same title","type":"note","tags":["one"]}',
    )
    first = import_markdown(repo, str(source), {})
    second = import_markdown(repo, str(source), {})
    assert first.doc_id == "same-title"
    assert second.doc_id == "same-title-2"
