"""Auto-commit Git das operações que alteram o acervo (config [git] auto_commit).

Regra de ouro: este módulo só ESCREVE no git. Nunca lê do remoto, nunca faz
pull, rebase, reset, force push nem resolve conflito. A reconciliação com o
remoto é tarefa do script externo `lore-sync`, que roda sob o mesmo lock.

Cada operação mutante chama `commit_paths` com exatamente os caminhos que ela
tocou (adições, remoções e movimentações, que vêm como dois caminhos). Só esses
caminhos entram no índice, nunca sujeira solta na árvore.

Falha de rede ou git nunca invalida o salvamento local: o comando continua
bem-sucedido e o push fica pendente (visível em `lore doctor`).
"""

from __future__ import annotations

import fcntl
import os
import subprocess
import threading
from contextlib import contextmanager

# Timeout curto: rede lenta/corta não pode travar um comando local.
GIT_TIMEOUT = 10
LOCK_NAME = "git.lock"

# Caminhos tocados pela operação corrente (thread-local). Repo.save_atomic,
# repo.add_file e review._move registram aqui; o comando consolida no fim.
_touched = threading.local()


def _touched_set() -> set[str]:
    if not hasattr(_touched, "paths"):
        _touched.paths = set()
    return _touched.paths


def touch(path: str) -> None:
    """Registra caminho que a operação corrente alterou (criou/editou/removeu)."""
    _touched_set().add(os.path.abspath(path))


def touched_paths() -> list[str]:
    return sorted(_touched_set())


def clear_touched() -> None:
    _touched_set().clear()


@contextmanager
def tracked():
    """Delimita uma operação mutante: limpa o rastro e acumula os tocados."""
    clear_touched()
    yield


class GitError(RuntimeError):
    """Falha de operação git. Nunca propaga para o usuário como erro fatal."""


def _run(root: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(
            ["git", "-C", root, *args],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitError(f"git {' '.join(args)}: {exc}") from exc
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise GitError(f"git {' '.join(args)} falhou: {detail}")
    return result


def is_git_repo(root: str) -> bool:
    try:
        out = _run(root, "rev-parse", "--is-inside-work-tree").stdout.strip()
    except GitError:
        return False
    return out == "true"


def lock_path(root: str) -> str:
    return os.path.join(root, ".lore", LOCK_NAME)


@contextmanager
def repo_lock(root: str):
    """Lock exclusivo compartilhado entre auto-commit e lore-sync.

    Se o lock não puder ser adquirido, roda sem ele (commit é atômico por si;
    o lock reduz corrida, não é a garantia de correção).
    """
    path = lock_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    handle = open(path, "a+")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            pass  # sem lock: melhor entregar o commit do que falhar o comando
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        handle.close()


def auto_commit_enabled(config: dict) -> bool:
    """Flag [git] auto_commit. Aceita [privacy] legado por compatibilidade."""
    git = config.get("git", {})
    if isinstance(git, dict) and "auto_commit" in git:
        return bool(git.get("auto_commit"))
    privacy = config.get("privacy", {})
    return bool(privacy.get("auto_commit")) if isinstance(privacy, dict) else False


def _rel(root: str, path: str) -> str:
    return os.path.relpath(os.path.abspath(path), os.path.abspath(root))


def pending_push(root: str) -> int | None:
    """Commits locais à frente do upstream. None se não dá para determinar."""
    try:
        result = _run(root, "rev-list", "--count", "--left-only",
                      "@{upstream}...HEAD").stdout.strip()
        return int(result)
    except (GitError, ValueError):
        return None


def commit_paths(root: str, paths: list[str], action: str, subject: str) -> str | None:
    """Commit dos paths tocados + push oportunista. None se nada commitado.

    Retorna hash do commit, ou None quando não há o que commitar (desabilitado,
    sem git, sem mudança real). Levanta GitError só em cenários internos.
    """
    if not paths or not is_git_repo(root):
        return None
    rels = sorted(
        {
            rel
            for p in paths
            if not (rel := _rel(root, p)).startswith("..") and not os.path.isabs(rel)
        }
    )
    if not rels:
        return None
    with repo_lock(root):
        _run(root, "add", "--", *rels)
        staged = _run(root, "diff", "--cached", "--name-only").stdout.strip()
        if not staged:
            return None
        message = f"lore({action}): {subject}"
        _run(root, "commit", "-m", message, "--", *rels)
        commit_hash = _run(root, "rev-parse", "--short", "HEAD").stdout.strip()
        try:
            _push(root)
        except GitError:
            pass  # push pendente: doctor avisa, lore-sync reconcilia
        return commit_hash


def _push(root: str) -> None:
    """Push do HEAD para o upstream atual. Nunca força, nunca cria branch."""
    if pending_push(root) in (None, 0):
        return
    upstream = _run(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name",
                    "@{upstream}", check=False).stdout.strip()
    if not upstream or upstream.startswith("@{"):
        return  # sem upstream configurado: commit local fica, não é erro
    remote, _, branch = upstream.partition("/")
    _run(root, "push", remote, f"HEAD:{branch}")
