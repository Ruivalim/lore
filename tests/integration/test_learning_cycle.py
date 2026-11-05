"""Ciclo CLI completo: pesquisar, salvar, aprovar e reutilizar localmente."""

from lore import repo as repo_mod
from lore.cli import main
from lore.models import parse_doc
from lore.research import Source


QUESTION = "Como eu vejo as mensagens dos ultimos commits?"


def test_cli_learning_cycle_uses_global_repo(tmp_path, monkeypatch, capsys):
    root = tmp_path / "library"
    for dirname in ("knowledge", "drafts", "archive", ".lore"):
        (root / dirname).mkdir(parents=True)
    (root / ".lore" / "config.toml").write_text(
        '[retrieval]\nsemantic = false\n\n[research]\nenabled = true\n'
        'require_confirmation = true\nsearch_provider = "duckduckgo"\n'
        '',
        encoding="utf-8",
    )
    config_home = tmp_path / "config"
    global_path = config_home / "lore" / "config.yaml"
    global_path.parent.mkdir(parents=True)
    global_path.write_text(
        f'repository:\n  root: "{root}"\nllm:\n  agent: pi\n  model: test/model\n',
        encoding="utf-8",
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.chdir(outside)

    searches = []

    def fake_search(self, query, max_results=5):
        searches.append(query)
        return [
            Source(
                url="https://git-scm.com/docs/git-log",
                title="git-log Documentation",
                accessed_at="2026-09-25",
            )
        ]

    monkeypatch.setattr("lore.research.DuckDuckGoWebSearch.search", fake_search)
    monkeypatch.setattr(
        "lore.research.fetch_page",
        lambda url: "git log --format=%s mostra mensagens dos commits recentes.",
    )
    model_calls = []

    def fake_complete(self, prompt, system=""):
        model_calls.append((prompt, self.binary, self.model))
        return (
            "RESPOSTA provisória: use `git log --format=%s`.\n\n"
            "CITAÇÕES: git-log Documentation.\n\n"
            "CONCLUSÕES DO MODELO: nenhuma.\n\nINCERTEZAS: nenhuma."
        )

    monkeypatch.setattr("lore.agents.Agent.complete", fake_complete)

    assert main(["ask", QUESTION, "--yes"]) == 0
    first_output = capsys.readouterr().out
    assert "Resposta externa, ainda não verificada" in first_output
    assert "Rascunho salvo" in first_output
    assert searches == [QUESTION]
    assert model_calls and model_calls[0][1:] == ("pi", "test/model")

    drafts = list((root / "drafts").glob("*.md"))
    assert len(drafts) == 1
    draft = parse_doc(drafts[0].read_text(encoding="utf-8"), str(drafts[0]))
    assert draft.valid and draft.status == "draft"
    assert draft.front["sources"][0]["url"] == "https://git-scm.com/docs/git-log"

    assert main(["approve", draft.id, "--human"]) == 0
    capsys.readouterr()
    promoted = repo_mod.find_by_id(repo_mod.Repo(str(root)), draft.id)
    assert promoted is not None and promoted.status == "verified"

    searches.clear()
    model_calls.clear()
    assert main(["ask", QUESTION, "--local-only", "--extractive"]) == 0
    local_output = capsys.readouterr().out
    assert "git log --format=%s" in local_output
    assert draft.id in local_output
    assert searches == []
    assert model_calls == []
