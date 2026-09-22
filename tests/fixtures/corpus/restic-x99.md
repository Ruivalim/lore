---
id: restic-x99
title: Backup do X99 com restic
type: howto
status: verified
tags:
  - linux
  - backup
  - restic
created_at: 2026-04-10
updated_at: 2026-04-11
verified_at: 2026-04-11
sources:
  - kind: personal
    description: Rotina semanal no X99 desde 2026-04-11
---

# Backup do X99 com restic

## Procedimento

Inicie o repositório com `restic init --repo /mnt/disco/backup`.

## Como verificar

`restic snapshots` lista os snapshots; `restic check` valida integridade.
