"""Sementes: documentos sobre o próprio Lore que todo acervo novo recebe.

O que quebra: semente citando comando, flag ou chave que não existe (doc que
mente), atualização passando por cima do que o usuário editou ou apagou,
semente reaparecendo depois de arquivada, e pergunta natural que não acha o
documento certo.
"""

import json
import os
import re
import subprocess

import pytest

from lore import config as config_mod
from lore import index as index_mod
from lore import repo as repo_mod
from lore import seed as seed_mod
from lore.answer import ask
from lore.cli import build_parser, main
from lore.models import parse_doc


@pytest.fixture()
def acervo(tmp_path):
    root = tmp_path / "acervo"
    assert main(["init", str(root), "--no-git", "--no-seed"]) == 0
    return repo_mod.Repo(str(root))


def _all_seed_text():
    for lang in seed_mod.LANGS:
        for doc_id, name, text in seed_mod.shipped(lang):
            yield lang, doc_id, text


# --- conteúdo -----------------------------------------------------------------

@pytest.mark.parametrize("lang", seed_mod.LANGS)
def test_seeds_are_valid_verified_and_summarized(lang):
    docs = seed_mod.shipped(lang)
    assert len(docs) >= 7
    for doc_id, name, text in docs:
        doc = parse_doc(text, name)
        assert doc.valid, (name, doc.errors)
        assert doc.status == "verified" and doc.front["reviewed_by"] == "human"
        assert "lore" in doc.front["tags"] and doc.front.get("summary")
        assert name == f"{doc_id}.md"


def test_both_languages_cover_the_same_topics_with_distinct_ids():
    pt = [doc_id for doc_id, _, _ in seed_mod.shipped("pt")]
    en = [doc_id for doc_id, _, _ in seed_mod.shipped("en")]
    assert len(pt) == len(en)
    assert not set(pt) & set(en)  # as duas podem conviver no mesmo acervo


def _parser_surface():
    parser = build_parser()
    commands, flags = set(), set(parser._option_string_actions)
    for action in parser._actions:
        if hasattr(action, "choices") and isinstance(action.choices, dict):
            for name, sub in action.choices.items():
                commands.add(name)
                flags |= set(sub._option_string_actions)
    return commands, flags


def test_seeds_only_mention_real_commands_and_flags():
    commands, flags = _parser_surface()
    for lang, doc_id, text in _all_seed_text():
        for command in re.findall(r"`lore ([a-z]+)", text):
            assert command in commands, f"{lang}/{doc_id}: lore {command}"
        for line in re.findall(r"`lore [^`]*`|^lore .*$", text, flags=re.MULTILINE):
            for flag in re.findall(r"(?<![\w-])(--[a-z][a-z-]*)", line):
                assert flag in flags, f"{lang}/{doc_id}: {flag} em {line!r}"


def test_seeds_only_mention_real_config_keys():
    defaults = config_mod.DEFAULTS
    for lang, doc_id, text in _all_seed_text():
        for section, key in re.findall(r"`(\w+)\.(\w+)(?: = [^`]*)?`", text):
            if section in ("llm",) and key in config_mod.LLM_TASKS:
                continue
            if section not in defaults:
                continue  # nome de arquivo, como index.sqlite
            assert key in defaults[section], f"{lang}/{doc_id}: {section}.{key}"
        for header in re.findall(r"^\[([\w.<>-]+)\]$|`\[([\w.<>-]+)\]`", text,
                                 flags=re.MULTILINE):
            name = header[0] or header[1]
            top, _, rest = name.partition(".")
            if top == "agents":
                continue
            assert top in defaults, f"{lang}/{doc_id}: [{name}]"
            if top == "llm" and rest:
                assert rest in config_mod.LLM_TASKS, f"{lang}/{doc_id}: [{name}]"


# --- instalação e atualização -------------------------------------------------

def _actions(results):
    return {item["id"]: item["action"] for item in results}


def test_install_then_reinstall_is_idempotent(acervo):
    first = seed_mod.install(acervo)
    assert set(_actions(first).values()) == {"added"}
    assert os.path.isdir(os.path.join(acervo.root, "knowledge", "lore"))
    assert set(_actions(seed_mod.install(acervo)).values()) == {"unchanged"}
    assert seed_mod.installed_lang(acervo.root) == "pt"


def test_edited_seed_is_kept_unless_force(acervo):
    seed_mod.install(acervo)
    doc_id, name, original = seed_mod.shipped("pt")[0]
    path = os.path.join(acervo.root, seed_mod.TARGET, name)
    edited = original.replace("# ", "# Minha versão: ", 1)
    open(path, "w", encoding="utf-8").write(edited)

    assert _actions(seed_mod.install(acervo))[doc_id] == "modified"
    assert open(path, encoding="utf-8").read() == edited
    assert _actions(seed_mod.install(acervo, force=True))[doc_id] == "updated"
    assert open(path, encoding="utf-8").read() == original


def test_untouched_seed_is_updated_when_lore_ships_a_new_version(acervo):
    seed_mod.install(acervo)
    doc_id, name, current = seed_mod.shipped("pt")[0]
    path = os.path.join(acervo.root, seed_mod.TARGET, name)
    old = current.replace("seed: 0.1.0", "seed: 0.0.9")
    open(path, "w", encoding="utf-8").write(old)
    state_path = os.path.join(acervo.root, seed_mod.STATE)
    state = json.load(open(state_path, encoding="utf-8"))
    state["files"][os.path.relpath(path, acervo.root)] = seed_mod._hash(old)
    json.dump(state, open(state_path, "w", encoding="utf-8"))

    assert _actions(seed_mod.install(acervo))[doc_id] == "updated"
    assert open(path, encoding="utf-8").read() == current


def test_deleted_seed_stays_deleted_unless_force(acervo):
    seed_mod.install(acervo)
    doc_id, name, _ = seed_mod.shipped("pt")[0]
    path = os.path.join(acervo.root, seed_mod.TARGET, name)
    os.remove(path)
    assert _actions(seed_mod.install(acervo))[doc_id] == "removed"
    assert not os.path.exists(path)
    assert _actions(seed_mod.install(acervo, force=True))[doc_id] == "added"


def test_archived_seed_is_not_reinstalled(acervo):
    seed_mod.install(acervo)
    doc_id = seed_mod.shipped("pt")[0][0]
    from lore import review as review_mod

    review_mod.archive(acervo, doc_id, human=True)
    assert _actions(seed_mod.install(acervo, force=True))[doc_id] == "elsewhere"
    assert repo_mod.find_by_id(acervo, doc_id).status == "archived"


def test_corrupt_state_file_is_treated_as_fresh_and_never_overwrites(acervo):
    seed_mod.install(acervo)
    open(os.path.join(acervo.root, seed_mod.STATE), "w").write("{quebrado")
    doc_id, name, original = seed_mod.shipped("pt")[0]
    path = os.path.join(acervo.root, seed_mod.TARGET, name)
    open(path, "w", encoding="utf-8").write(original + "\nNota minha.\n")
    # Sem estado não dá para provar que o arquivo é intocado: não sobrescreve.
    assert _actions(seed_mod.install(acervo))[doc_id] == "modified"


def test_unknown_language_is_rejected(acervo):
    with pytest.raises(ValueError, match="língua desconhecida"):
        seed_mod.install(acervo, "fr")


# --- CLI ----------------------------------------------------------------------

def test_init_seeds_by_default_and_respects_flags(tmp_path, capsys):
    assert main(["init", str(tmp_path / "a"), "--no-git"]) == 0
    assert "documentos sobre o próprio Lore" in capsys.readouterr().out
    assert len(os.listdir(tmp_path / "a" / "knowledge" / "lore")) == len(seed_mod.shipped("pt"))

    assert main(["init", str(tmp_path / "b"), "--no-git", "--no-seed"]) == 0
    assert not (tmp_path / "b" / "knowledge" / "lore").exists()

    assert main(["init", str(tmp_path / "c"), "--no-git", "--lang", "en"]) == 0
    names = os.listdir(tmp_path / "c" / "knowledge" / "lore")
    assert "lore-asking-questions.md" in names


def test_seed_command_json_and_language_memory(acervo, capsys):
    assert main(["--root", acervo.root, "--json", "seed", "--lang", "en"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["lang"] == "en"
    assert {item["action"] for item in payload["results"]} == {"added"}
    assert main(["--root", acervo.root, "--json", "seed"]) == 0
    assert json.loads(capsys.readouterr().out)["lang"] == "en"


def test_seed_command_auto_commits(acervo, capsys):
    def git(*args):
        return subprocess.run(["git", "-C", acervo.root, *args], capture_output=True,
                              text=True, check=True).stdout

    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    config = os.path.join(acervo.root, ".lore", "config.toml")
    text = open(config, encoding="utf-8").read()
    assert "auto_commit = false" in text  # template já tem [git]; outro [git] é TOML inválido
    open(config, "w", encoding="utf-8").write(text.replace("auto_commit = false",
                                                           "auto_commit = true"))
    assert main(["--root", acervo.root, "seed"]) == 0
    committed = git("show", "--name-only", "--format=%s", "HEAD").split("\n")
    assert committed[0].startswith("lore(seed):")
    assert sum(1 for line in committed if line.startswith("knowledge/lore/")) == len(
        seed_mod.shipped("pt"))


# --- recuperação: pergunta natural acha o documento ---------------------------

QUESTIONS = {
    "pt": {
        "como aprovo um rascunho": "lore-revisar-rascunhos",
        "como rejeito um rascunho": "lore-revisar-rascunhos",
        "como troco o modelo": "lore-configurar-agentes",
        "como vejo a resposta completa": "lore-como-perguntar",
        "quais os atalhos do tui": "lore-atalhos-do-tui",
        "como ligo a pesquisa na internet": "lore-pesquisa-externa",
        "como sincronizo entre máquinas": "lore-git-e-sincronizacao",
        "quais campos o front matter precisa": "lore-escrever-documentos",
    },
    "en": {
        "how do I approve a draft": "lore-reviewing-drafts",
        "how do I change the model": "lore-configuring-agents",
        "how do I see the full answer": "lore-asking-questions",
        "what are the tui shortcuts": "lore-tui-shortcuts",
        "how do I turn on web research": "lore-external-research",
        "how do I sync between machines": "lore-git-and-sync",
        "which front matter fields are required": "lore-writing-documents",
    },
}


@pytest.mark.parametrize("lang", seed_mod.LANGS)
def test_natural_questions_find_the_right_seed(acervo, lang):
    seed_mod.install(acervo, lang)
    index_mod.build(acervo)
    for question, expected in QUESTIONS[lang].items():
        answer = ask(acervo, question, extractive=True, local_only=True)
        assert answer.citations, question
        assert expected in answer.citations[0], (question, answer.citations)
