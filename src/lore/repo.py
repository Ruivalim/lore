"""Operações sobre o repositório Markdown: fonte canônica (README §10.2)."""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass

from .models import Doc, parse_doc

KNOWLEDGE = "knowledge"
DRAFTS = "drafts"
ARCHIVE = "archive"

MANAGED_DIRS = (KNOWLEDGE, DRAFTS, ARCHIVE)


@dataclass
class Repo:
    root: str

    def managed_dir(self, name: str) -> str:
        return os.path.join(self.root, name)


def find_root(start: str = "") -> str:
    """Sobe até achar raiz lore (dir com knowledge/ ou .lore/). Senão, cwd."""
    current = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.isdir(os.path.join(current, KNOWLEDGE)) or os.path.isdir(
            os.path.join(current, ".lore")
        ):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return os.getcwd()
        current = parent


def _safe_join(root: str, *parts: str) -> str:
    """Junta caminho e garante permanência dentro da raiz (sem traversal)."""
    target = os.path.realpath(os.path.join(root, *parts))
    real_root = os.path.realpath(root)
    if target != real_root and not target.startswith(real_root + os.sep):
        raise ValueError(f"caminho fora do repositório: {os.path.join(*parts)}")
    return target


def check_path(root: str, path: str) -> str:
    """Valida caminho de arquivo contra traversal e symlink fugitivo."""
    if os.path.isabs(path):
        candidate = os.path.realpath(path)
        real_root = os.path.realpath(root)
        if candidate != real_root and not candidate.startswith(real_root + os.sep):
            raise ValueError(f"caminho fora do repositório: {path}")
        return candidate
    return _safe_join(root, path)


def iter_doc_files(repo: Repo) -> list[str]:
    """Lista .md sob knowledge/, drafts/, archive/ em ordem determinística."""
    found: list[str] = []
    for dirname in MANAGED_DIRS:
        base = repo.managed_dir(dirname)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames.sort()
            # Ignora symlink de diretório que escape da raiz.
            dirnames[:] = [
                name
                for name in dirnames
                if os.path.realpath(os.path.join(dirpath, name)).startswith(
                    os.path.realpath(repo.root) + os.sep
                )
            ]
            for name in sorted(filenames):
                if name.endswith(".md"):
                    full = os.path.join(dirpath, name)
                    if os.path.realpath(full).startswith(
                        os.path.realpath(repo.root) + os.sep
                    ):
                        found.append(full)
    return found


def load_all(repo: Repo) -> list[Doc]:
    docs: list[Doc] = []
    for path in iter_doc_files(repo):
        with open(path, encoding="utf-8") as handle:
            docs.append(parse_doc(handle.read(), path))
    return docs


def find_by_id(repo: Repo, doc_id: str) -> Doc | None:
    wanted = doc_id.lower()
    for doc in load_all(repo):
        if doc.id.lower() == wanted:
            return doc
    return None


def duplicate_ids(repo: Repo) -> dict[str, list[str]]:
    seen: dict[str, list[str]] = {}
    for path in iter_doc_files(repo):
        with open(path, encoding="utf-8") as handle:
            doc = parse_doc(handle.read(), path)
        if doc.id:
            seen.setdefault(doc.id.lower(), []).append(path)
    return {doc_id: paths for doc_id, paths in seen.items() if len(paths) > 1}


def save_atomic(path: str, text: str) -> None:
    """Escrita atômica: tmp + fsync + rename. Sem documento parcial."""
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def render_doc(front: dict, body: str) -> str:
    lines = ["---"]
    for key, value in front.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                if isinstance(item, dict):
                    sub = list(item.items())
                    first_key, first_val = sub[0]
                    lines.append(f"  - {first_key}: {first_val}")
                    for sub_key, sub_val in sub[1:]:
                        lines.append(f"    {sub_key}: {sub_val}")
                else:
                    lines.append(f"  - {item}")
        elif value is None:
            lines.append(f"{key}: null")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")
    lines.append(body.lstrip("\n"))
    if not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    return "\n".join(lines)


def add_file(
    repo: Repo, source: str, dest_dir: str = DRAFTS, move: bool = False
) -> str:
    """Importa Markdown externo. Valida antes; original segue intacto (sem --move)."""
    if dest_dir not in MANAGED_DIRS:
        raise ValueError(f"destino inválido: {dest_dir}")
    src = source
    if not os.path.isabs(src):
        src = os.path.join(os.getcwd(), src)
    src = os.path.realpath(src)
    if not os.path.isfile(src):
        raise FileNotFoundError(f"arquivo não encontrado: {source}")
    with open(src, encoding="utf-8") as handle:
        doc = parse_doc(handle.read(), src)
    if not doc.valid:
        raise ValueError(f"documento inválido: {'; '.join(doc.errors)}")
    existing = find_by_id(repo, doc.id)
    if existing is not None:
        raise ValueError(f"id duplicado: {doc.id} já existe em {existing.path}")
    dest = _safe_join(repo.root, dest_dir, os.path.basename(src))
    if os.path.exists(dest):
        raise ValueError(f"destino já existe: {dest}")
    if move:
        shutil.move(src, dest)
    else:
        shutil.copy2(src, dest)
    return dest
