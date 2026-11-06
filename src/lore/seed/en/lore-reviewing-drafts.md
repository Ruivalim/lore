---
id: lore-reviewing-drafts
title: Reviewing, approving and rejecting drafts
summary: `lore review` lists what waits for review; approve with `lore approve <id> --human` and reject with `lore reject <id> --reason "why" --human`.
type: howto
status: verified
reviewed_by: human
seed: 0.1.0
tags:
  - lore
  - review drafts
created_at: 2026-11-05
updated_at: 2026-11-05
verified_at: 2026-11-05
review_after: 2027-05-05
sources:
  - url: https://github.com/Ruivalim/lore
    title: Lore, README and config.example.toml
    accessed_at: 2026-11-05
---

# Reviewing, approving and rejecting drafts

## Questions this document answers

How do I approve a draft? How do I reject a draft? Where do I see what needs
review? Can drafts be approved automatically? What is `reviewed_by: auto`?
How do I reactivate an outdated (stale) document?

## Procedure

```sh
lore review                      # queue: drafts, stale, overdue, auto-approved
lore review <id>                 # detail: unsourced passages and possible conflicts
lore edit <id>                   # opens it in $EDITOR
lore approve <id> --human        # becomes verified and moves to knowledge/
lore reject <id> --reason "why" --human   # moves to archive/ with the reason
```

In the TUI, `v` filters drafts, `A` approves (asks to confirm), `R` rejects
(asks for the reason) and `e` edits.

## States

A `draft` becomes `verified` or `archived`. A `verified` document can become
`stale` (`lore stale <id> --human`), which still answers but with a warning,
and `verified` or `stale` documents can be archived
(`lore archive <id> --human`). Reviewed a `stale` document and it still
holds? `lore approve <id> --human` makes it `verified` again and moves
`review_after` forward by the same interval as before. Past its
`review_after` date, a document shows up in the queue as overdue.

## Automatic approval

Each source of drafts has a policy in `[review]`:

```toml
[review]
import = "human"      # human | auto-if-clean | auto
research = "human"
```

`auto-if-clean` approves research only with a web source, no unsourced
passage, no page dropped for injection and no conflict; for imports it only
checks conflicts. `auto` approves any valid draft. Anything approved this way
gets `reviewed_by: auto` and stays in the queue until
`lore approve <id> --human` confirms it.
