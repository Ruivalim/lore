---
id: lore-git-and-sync
title: The base in Git and syncing
summary: `lore init <path>` creates the base with git; with `git.auto_commit = true` every change is committed and pushed if the branch has an upstream.
type: howto
status: verified
reviewed_by: human
seed: 0.1.0
tags:
  - lore
  - git sync
created_at: 2026-11-05
updated_at: 2026-11-05
verified_at: 2026-11-05
review_after: 2027-05-05
sources:
  - url: https://github.com/Ruivalim/lore
    title: Lore, README and config.example.toml
    accessed_at: 2026-11-05
---

# The base in Git and syncing

## Questions this document answers

How do I create a new base? How do I make lore commit on its own? How do I
sync between machines? Why does doctor say there are unpushed commits?

## Procedure

```sh
lore init ~/notes          # knowledge/, drafts/, archive/, .lore/ and git init
```

Outside the base, lore uses `repository.root` from
`~/.config/lore/config.yaml`. Inside it, the root is found automatically;
`--root` forces another one.

With `git.auto_commit = true`, every command that changes files commits only
what it touched and pushes if the branch has an upstream. lore never pulls,
rebases or force pushes. To write from more than one machine, the `lore-sync`
script in lore's repository pulls with rebase, reindexes and pushes, under the
same lock.

A failed push stays pending and `lore doctor` says how many commits are
waiting.

## Index

The index in `.lore/index.sqlite` is disposable: `lore reindex` rebuilds it
from the files. `.lore/` stays out of Git.
