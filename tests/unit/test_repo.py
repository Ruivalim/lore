"""Repositório: escrita atômica, segurança de caminho, add, duplicados."""

import os

import pytest

from lore import repo as repo_mod


def test_discover_root_walks_up_and_returns_none_outside_repo(tmp_path, monkeypatch):
    root = tmp_path / "library"
    nested = root / "notes" / "deep"
    (root / "knowledge").mkdir(parents=True)
    nested.mkdir(parents=True)

    assert repo_mod.discover_root(str(nested)) == str(root)

    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.chdir(outside)
    assert repo_mod.discover_root() is None


def test_resolve_root_precedence_and_validation(tmp_path):
    explicit = tmp_path / "explicit"
    discovered = tmp_path / "discovered"
    configured = tmp_path / "configured"
    for root in (explicit, discovered, configured):
        (root / "knowledge").mkdir(parents=True)
    nested = discovered / "nested"
    nested.mkdir()

    assert repo_mod.resolve_root(
        explicit=str(explicit), start=str(nested), configured=str(configured)
    ) == str(explicit)
    assert repo_mod.resolve_root(start=str(nested), configured=str(configured)) == str(
        discovered
    )
    assert repo_mod.resolve_root(start=str(tmp_path), configured=str(configured)) == str(
        configured
    )

    with pytest.raises(ValueError, match="repositório Lore"):
        repo_mod.resolve_root(start=str(tmp_path), configured=str(tmp_path / "missing"))
    with pytest.raises(ValueError, match="nenhum repositório Lore"):
        repo_mod.resolve_root(start=str(tmp_path))


def test_load_all_and_find(lore_repo):
    repo = repo_mod.Repo(lore_repo)
    docs = repo_mod.load_all(repo)
    assert len(docs) == 3
    found = repo_mod.find_by_id(repo, "Wireguard-Split-DNS")
    assert found is not None
    assert found.valid
    assert found.path.endswith("wireguard-split-dns.md")


def test_duplicate_ids(lore_repo):
    repo = repo_mod.Repo(lore_repo)
    assert repo_mod.duplicate_ids(repo) == {}
    dup = os.path.join(lore_repo, "drafts", "copia.md")
    with open(os.path.join(lore_repo, "knowledge", "wireguard-split-dns.md"), encoding="utf-8") as handle:
        content = handle.read()
    with open(dup, "w", encoding="utf-8") as handle:
        handle.write(content)
    dups = repo_mod.duplicate_ids(repo)
    assert "wireguard-split-dns" in dups
    assert len(dups["wireguard-split-dns"]) == 2


def test_save_atomic_no_partial(tmp_path):
    target = str(tmp_path / "doc.md")
    repo_mod.save_atomic(target, "conteúdo\n")
    with open(target, encoding="utf-8") as handle:
        assert handle.read() == "conteúdo\n"
    leftovers = [name for name in os.listdir(tmp_path) if name.endswith(".tmp")]
    assert leftovers == []


def test_save_atomic_new_never_overwrites(tmp_path):
    target = str(tmp_path / "doc.md")
    repo_mod.save_atomic_new(target, "primeiro\n")
    with pytest.raises(FileExistsError):
        repo_mod.save_atomic_new(target, "segundo\n")
    assert (tmp_path / "doc.md").read_text(encoding="utf-8") == "primeiro\n"
    assert not list(tmp_path.glob("*.tmp"))


def test_check_path_blocks_traversal(empty_repo):
    with pytest.raises(ValueError):
        repo_mod.check_path(empty_repo, "../fora.md")
    with pytest.raises(ValueError):
        repo_mod.check_path(empty_repo, "/etc/passwd")


def test_check_path_blocks_escaping_symlink(empty_repo, tmp_path):
    # tmp_path == raiz de empty_repo (mesmo fixture): sair de verdade.
    outside = os.path.join(os.path.dirname(empty_repo), "fora_repo.md")
    with open(outside, "w", encoding="utf-8") as handle:
        handle.write("x")
    link = os.path.join(empty_repo, "drafts", "atalho.md")
    os.symlink(str(outside), link)
    with pytest.raises(ValueError):
        repo_mod.check_path(empty_repo, "drafts/atalho.md")


def test_add_file_copies_and_validates(empty_repo, tmp_path):
    from tests.conftest import VALID_NOTE

    src = tmp_path / "novo.md"
    src.write_text(VALID_NOTE.replace("ideia-backup", "novo-doc"), encoding="utf-8")
    repo = repo_mod.Repo(empty_repo)
    dest = repo_mod.add_file(repo, str(src), "drafts")
    assert os.path.isfile(dest)
    assert os.path.isfile(str(src))  # original intacto
    assert repo_mod.find_by_id(repo, "novo-doc") is not None


def test_add_invalid_rejected_file_kept(empty_repo, tmp_path):
    from tests.conftest import INVALID_NO_ID

    src = tmp_path / "ruim.md"
    src.write_text(INVALID_NO_ID, encoding="utf-8")
    repo = repo_mod.Repo(empty_repo)
    with pytest.raises(ValueError):
        repo_mod.add_file(repo, str(src), "drafts")
    assert repo_mod.load_all(repo) == []


def test_add_duplicate_id_rejected(lore_repo, tmp_path):
    from tests.conftest import VALID_NOTE

    src = tmp_path / "outro.md"
    src.write_text(VALID_NOTE.replace("ideia-backup", "wireguard-split-dns").replace(
        "type: note", "type: howto").replace("sources: []",
        "sources:\n  - kind: personal\n    description: lab"), encoding="utf-8")
    repo = repo_mod.Repo(lore_repo)
    with pytest.raises(ValueError, match="duplicado"):
        repo_mod.add_file(repo, str(src), "drafts")
