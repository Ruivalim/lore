---
id: what-is-git-worktree
title: What is git worktree for
summary: It checks out several branches of one repository into separate directories at the same time, sharing a single object store.
type: research
status: draft
tags:
  - git
  - pesquisa-externa
created_at: 2026-11-05
updated_at: 2026-11-05
verified_at: null
review_after: 2026-11-05
sources:
  - url: https://git-scm.com/docs/git-worktree
    title: git-worktree documentation
    accessed_at: 2026-11-05
---

# What is git worktree for

## Question

What is git worktree for?

## External answer (not verified)

`git worktree add ../hotfix main` creates a second working directory on the
`main` branch while the current one stays on the feature branch.
[git-worktree documentation]

Both share the same object database, so nothing is cloned or downloaded again.

## Model conclusions

Useful when a long build or test run is going on in one branch and an urgent
fix is needed in another one.

## Uncertainties

Submodule support is still marked experimental in the documentation.
