"""Auto-commit git ([git] auto_commit): staging de paths, movimentos, lock, push.

Foco no que quebra: move gera dois caminhos (origem+destino), push que não pode
derrubar o comando, filtro de caminho fora da raiz, flag desligada = nada.
"""

import json
import os
import subprocess

import pytest

from lore import gitops
from lore.cli import main


def _git(root, *args):
    return subprocess.run(
        ["git", "-C", root, *args], capture_output=True, text=True, check=True
    )


@pytest.fixture()
def git_repo(tmp_path):
    """Repo Lore + git com commit inicial e identidade local."""
    for dirname in ("knowledge", "drafts", "archive"):
        (tmp_path / dirname).mkdir()
    (tmp_path / ".lore").mkdir()
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "seed.md").write_text("seed\n", encoding="utf-8")
    _git(tmp_path, "add", "seed.md")
    _git(tmp_path, "commit", "-qm", "chore: seed")
    return str(tmp_path)


def _enable_autocommit(root):
    path = os.path.join(root, ".lore", "config.toml")
    with open(path, "w", encoding="utf-8") as h:
        h.write("[git]\nauto_commit = true\n")


def _commit_files(root):
    out = _git(root, "show", "--name-only", "--format=", "HEAD").stdout
    return [line for line in out.splitlines() if line.strip()]


def _commit_name_status(root):
    """Linhas 'STATUS\torigem[\tdestino]' do HEAD. Renames mostram os 2 lados."""
    out = _git(root, "show", "--name-status", "--format=", "HEAD").stdout
    return [line for line in out.splitlines() if line.strip()]


def test_commit_paths_move_records_both_sides(git_repo):
    src = os.path.join(git_repo, "drafts", "a.md")
    dest_dir = os.path.join(git_repo, "knowledge")
    with open(src, "w", encoding="utf-8") as h:
        h.write("x\n")
    _git(git_repo, "add", "drafts/a.md")
    _git(git_repo, "commit", "-qm", "chore: a")

    os.rename(src, os.path.join(dest_dir, "a.md"))
    gitops.touch(src)
    gitops.touch(os.path.join(dest_dir, "a.md"))
    gitops.commit_paths(git_repo, gitops.touched_paths(), "approve", "a")

    entries = _commit_name_status(git_repo)
    joined = "\n".join(entries)
    assert "drafts/a.md" in joined  # origem (lado esquerdo do rename)
    assert "knowledge/a.md" in joined  # destino (lado direito do rename)


def test_commit_paths_ignores_outside_root(git_repo, tmp_path):
    # Fora do repo: irmão de tmp_path, não dentro dele.
    outside = tmp_path.parent / "externo.md"
    outside.write_text("x\n", encoding="utf-8")
    inside = os.path.join(git_repo, "knowledge", "b.md")
    with open(inside, "w", encoding="utf-8") as h:
        h.write("y\n")

    gitops.commit_paths(git_repo, [str(outside), inside], "add", "b")
    files = _commit_files(git_repo)
    assert "knowledge/b.md" in files
    assert not any("externo" in f for f in files)
    outside.unlink()


def test_commit_paths_no_change_returns_none(git_repo):
    seed = os.path.join(git_repo, "seed.md")
    assert gitops.commit_paths(git_repo, [seed], "edit", "noop") is None


def test_disabled_autocommit_no_commit(git_repo, capsys):
    # config.toml ausente = auto_commit false por padrão
    dest = os.path.join(git_repo, "drafts", "c.md")
    with open(dest, "w", encoding="utf-8") as h:
        h.write("z\n")
    before = _git(git_repo, "rev-list", "--count", "HEAD").stdout.strip()
    main(["--root", git_repo, "new", "--type", "note", "--title", "Teste C"])
    after = _git(git_repo, "rev-list", "--count", "HEAD").stdout.strip()
    assert before == after  # nenhum commit novo


def test_enabled_autocommit_commits_on_new(git_repo):
    _enable_autocommit(git_repo)
    before = _git(git_repo, "rev-list", "--count", "HEAD").stdout.strip()
    assert main(["--root", git_repo, "new", "--type", "note", "--title", "Doc Novo"]) == 0
    after = _git(git_repo, "rev-list", "--count", "HEAD").stdout.strip()
    assert int(after) == int(before) + 1
    files = _commit_files(git_repo)
    assert any(f.endswith("doc-novo.md") for f in files)


def test_enabled_autocommit_move_commit_two_paths(git_repo):
    _enable_autocommit(git_repo)
    mover = os.path.join(git_repo, "drafts", "mover.md")
    with open(mover, "w", encoding="utf-8") as h:
        h.write(
            "---\nid: mover\ntitle: Mover\ntype: note\nstatus: draft\n"
            "tags:\n  - t\ncreated_at: 2026-01-01\nupdated_at: 2026-01-01\n"
            "verified_at: null\nsources: []\n---\n\n# Mover\n\n## Nota\n\nCorpo.\n"
        )
    _git(git_repo, "add", "drafts/mover.md")
    _git(git_repo, "commit", "-qm", "chore: mover")
    assert main(["--root", git_repo, "approve", "mover", "--human"]) == 0
    joined = "\n".join(_commit_name_status(git_repo))
    assert "drafts/mover.md" in joined
    assert "knowledge/mover.md" in joined


def test_push_failure_does_not_raise(git_repo, monkeypatch):
    # Sem upstream configurado: commit local acontece, push é pulado sem erro.
    _enable_autocommit(git_repo)
    assert main(["--root", git_repo, "new", "--type", "note", "--title", "Sem Push"]) == 0
    assert gitops.pending_push(git_repo) is None  # sem upstream: indeterminado


def test_auto_commit_enabled_legacy_privacy():
    assert gitops.auto_commit_enabled({"privacy": {"auto_commit": True}})
    assert not gitops.auto_commit_enabled({"privacy": {"auto_commit": False}})
    assert gitops.auto_commit_enabled({"git": {"auto_commit": True}})
    # [git] tem precedência sobre [privacy]
    assert not gitops.auto_commit_enabled(
        {"git": {"auto_commit": False}, "privacy": {"auto_commit": True}}
    )


def test_doctor_reports_pending_push(git_repo, tmp_path, capsys):
    """Push que falha deixa o commit local e o doctor precisa contar ele."""
    remote = tmp_path.parent / f"{tmp_path.name}-remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    branch = _git(git_repo, "branch", "--show-current").stdout.strip()
    _git(git_repo, "remote", "add", "origin", str(remote))
    _git(git_repo, "push", "-q", "-u", "origin", branch)
    remote.rename(remote.with_name(remote.name + ".fora"))  # remoto inacessível
    _enable_autocommit(git_repo)

    assert main(["--root", git_repo, "new", "--type", "note", "--title", "Pendente"]) == 0
    capsys.readouterr()

    assert gitops.pending_push(git_repo) == 1
    main(["--root", git_repo, "doctor", "--json"])
    warnings = json.loads(capsys.readouterr().out)["warnings"]
    assert any("1 commit(s)" in item for item in warnings)


def test_repo_lock_is_exclusive(git_repo):
    import fcntl

    path = gitops.lock_path(git_repo)
    with open(path, "a+") as a:
        fcntl.flock(a.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        # segundo acquire com LOCK_NB deve falhar enquanto o primeiro segura
        with open(path, "a+") as b:
            with pytest.raises(OSError):
                fcntl.flock(b.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(a.fileno(), fcntl.LOCK_UN)


def test_write_pushes_to_upstream_without_pull(git_repo, tmp_path):
    """Escritor único: cada escrita chega ao remoto sem timer nem pull."""
    remote = tmp_path.parent / f"{tmp_path.name}-remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    branch = _git(git_repo, "branch", "--show-current").stdout.strip()
    _git(git_repo, "remote", "add", "origin", str(remote))
    _git(git_repo, "push", "-q", "-u", "origin", branch)
    _enable_autocommit(git_repo)

    assert main(["--root", git_repo, "new", "--type", "note", "--title", "Sobe"]) == 0

    local = _git(git_repo, "rev-parse", "HEAD").stdout.strip()
    pushed = subprocess.run(
        ["git", "-C", str(remote), "rev-parse", branch],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert pushed == local
    assert gitops.pending_push(git_repo) == 0


def test_commit_survives_path_created_and_moved_before_commit(git_repo):
    """Auto-aprovação cria em drafts/ e move para knowledge/ antes do commit:
    o caminho de origem nunca existiu no git e não pode derrubar o commit."""
    os.makedirs(os.path.join(git_repo, "knowledge"), exist_ok=True)
    dest = os.path.join(git_repo, "knowledge", "x.md")
    with open(dest, "w", encoding="utf-8") as handle:
        handle.write("x\n")
    ghost = os.path.join(git_repo, "drafts", "x.md")  # nunca existiu no git
    commit = gitops.commit_paths(git_repo, [ghost, dest], "import", "x")
    assert commit
    assert _commit_files(git_repo) == ["knowledge/x.md"]
