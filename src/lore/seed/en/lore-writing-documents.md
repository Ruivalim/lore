---
id: lore-writing-documents
title: Writing and importing documents
summary: Create one with `lore new --type howto --title "Title"` or import any Markdown with `lore import note.md`; every document has front matter with id, title, type, status, tags, dates and sources.
type: reference
status: verified
reviewed_by: human
seed: 0.1.0
tags:
  - lore
  - documents front-matter
created_at: 2026-11-05
updated_at: 2026-11-05
verified_at: 2026-11-05
review_after: 2027-05-05
sources:
  - url: https://github.com/Ruivalim/lore
    title: Lore, README and config.example.toml
    accessed_at: 2026-11-05
---

# Writing and importing documents

## Questions this document answers

How do I create a new document? How do I import a note I already have? Which
front matter fields are required? Which types exist? How do I cite a source?

## Create and import

```sh
lore new --type howto --title "Rotate SSH keys"   # draft from the template
lore import note.md     # the agent suggests title, type, tags and summary
lore add note.md        # a file that already has lore front matter
```

Everything starts in `drafts/` and only answers after approval.

## Front matter

Required: `id` (lowercase slug), `title`, `type`, `status`, `tags`,
`created_at`, `updated_at` and `sources`. A `verified` document also needs
`verified_at`. Optional: `summary` (the short answer, up to 600 characters),
`review_after`, `supersedes` and `related`.

Types: `howto`, `troubleshooting`, `reference`, `concept`, `decision`,
`research` and `note`. States: `draft`, `verified`, `stale` and `archived`.

## Sources

Each item in `sources` is one of:

- web: `url`, `title` and `accessed_at`;
- your own experience: `kind: personal` and `description`;
- a local file: `kind: local`, `path` and `description`.

An empty `sources` is only allowed for `note`. Use block lists (one `-` item
per line); bracket lists are not accepted.
