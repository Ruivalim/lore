---
id: backup-retention
title: Backup retention policy
summary: Keep 7 daily, 4 weekly and 12 monthly snapshots, and prune only after a successful check.
type: decision
status: verified
reviewed_by: human
tags:
  - backup
  - restic
created_at: 2026-07-11
updated_at: 2026-07-11
verified_at: 2026-07-11
review_after: 2027-01-11
sources:
  - url: https://restic.readthedocs.io/en/stable/060_forget.html
    title: restic, removing backup snapshots
    accessed_at: 2026-07-11
---

# Backup retention policy

## Decision

Keep 7 daily, 4 weekly and 12 monthly snapshots:

```sh
restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 12 --prune
```

## Why

A year of monthly points covers slow corruption that nobody notices for weeks.
Pruning runs only after `restic check` passes, so a damaged repository is
never compacted.
