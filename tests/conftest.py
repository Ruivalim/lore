"""Fixture: repo lore temporário com docs válidos e inválidos."""

import pytest


@pytest.fixture(autouse=True)
def isolate_user_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))


VALID_HOWTO = """\
---
id: wireguard-split-dns
title: Split DNS com WireGuard
type: howto
status: verified
tags:
  - linux
  - networking
created_at: 2026-01-10
updated_at: 2026-02-01
verified_at: 2026-02-01
review_after: 2027-02-01
sources:
  - kind: personal
    description: Verificado no homelab em 2026-02-01
---

# Split DNS com WireGuard

## Procedimento

Use `DNS = 10.0.0.53` no perfil do túnel.
"""

VALID_NOTE = """\
---
id: ideia-backup
title: Ideia de backup
type: note
status: draft
tags:
  - pessoal
created_at: 2026-03-01
updated_at: 2026-03-01
verified_at: null
sources: []
---

# Ideia de backup

## Nota

Testar restic no X99.
"""

INVALID_NO_ID = """\
---
title: Sem id
type: note
status: draft
tags:
  - x
created_at: 2026-03-01
updated_at: 2026-03-01
sources: []
---

# Sem id

## Nota

Nada.
"""


@pytest.fixture()
def lore_repo(tmp_path):
    for dirname in ("knowledge", "drafts", "archive"):
        (tmp_path / dirname).mkdir()
    (tmp_path / "knowledge" / "wireguard-split-dns.md").write_text(
        VALID_HOWTO, encoding="utf-8"
    )
    (tmp_path / "drafts" / "ideia-backup.md").write_text(VALID_NOTE, encoding="utf-8")
    (tmp_path / "drafts" / "sem-id.md").write_text(INVALID_NO_ID, encoding="utf-8")
    (tmp_path / ".lore").mkdir()
    (tmp_path / ".lore" / "config.toml").write_text(
        "[git]\nauto_commit = false\n", encoding="utf-8"
    )
    return str(tmp_path)


@pytest.fixture()
def empty_repo(tmp_path):
    for dirname in ("knowledge", "drafts", "archive"):
        (tmp_path / dirname).mkdir()
    return str(tmp_path)
