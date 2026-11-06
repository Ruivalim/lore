---
id: git-recent-commit-subjects
title: Show only the subjects of recent commits
summary: Run `git log --format=%s -10` to print just the subject line of the last 10 commits.
type: howto
status: verified
reviewed_by: human
tags:
  - git
  - cli
created_at: 2026-10-02
updated_at: 2026-10-02
verified_at: 2026-10-02
review_after: 2027-10-02
sources:
  - url: https://git-scm.com/docs/git-log#_pretty_formats
    title: git-log pretty formats
    accessed_at: 2026-10-02
---

# Show only the subjects of recent commits

## Procedure

Use `git log --format=%s -10` to list only the subject of the last 10 commits.
Add `--no-merges` to hide merge commits.

```sh
git log --format=%s -10 --no-merges
```

## Variations

`git log --oneline` also prints the abbreviated hash before each subject.
