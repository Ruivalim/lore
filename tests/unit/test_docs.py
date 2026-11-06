"""O que a documentação mostra precisa funcionar: exemplo do README e acervo
de exemplo. Doc que mente é pior que doc nenhuma."""

import re
from pathlib import Path

from lore import repo as repo_mod
from lore.cli import run_doctor
from lore.models import parse_doc

ROOT = Path(__file__).resolve().parents[2]


def test_readme_front_matter_example_is_valid():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    block = re.search(r"```markdown\n(.*?)```", readme, flags=re.DOTALL).group(1)
    doc = parse_doc(block + "\n# Título\n\nTexto.\n", "exemplo.md")
    assert doc.errors == []


def test_example_acervo_is_clean():
    repo = repo_mod.Repo(str(ROOT / "examples" / "acervo"))
    docs = repo_mod.load_all(repo)
    assert docs and all(doc.valid for doc in docs), [d.errors for d in docs]
    problems, _ = run_doctor(repo)
    assert problems == []
    assert {doc.status for doc in docs} >= {"verified", "draft"}
