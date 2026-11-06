---
id: lore-asking-questions
title: Asking lore questions
summary: Run `lore ask "question"` for a short answer with its source and `--full` for the complete one; with no question, `lore ask` opens the TUI.
type: howto
status: verified
reviewed_by: human
seed: 0.1.0
tags:
  - lore
  - ask search
created_at: 2026-11-05
updated_at: 2026-11-05
verified_at: 2026-11-05
review_after: 2027-05-05
sources:
  - url: https://github.com/Ruivalim/lore
    title: Lore, README and config.example.toml
    accessed_at: 2026-11-05
---

# Asking lore questions

## Questions this document answers

How do I ask a question? How do I see the full answer? What does coverage
mean? How do I search without a model? How do I stay inside the base?

## Procedure

Ask in plain language:

```sh
lore ask "how do I see the subjects of recent commits"
```

You get the short answer, one to three sentences, with the source as
`file#section`. Add `--full` for the complete answer. With no question,
`lore ask` opens the TUI.

Useful options:

- `--extractive`: calls no model and shows the matching passages;
- `--local-only`: never researches outside the base;
- `--type howto` and `--tag git`: restrict which documents are used;
- `--as-of 2026-01-01`: ignores documents updated after that date;
- `--json`: structured output, short answer in `short`, full one in `text`.

To see passages without a composed answer, use `lore search "terms"`.

## Coverage

Every answer says how much of the question the base covered:

- `sufficient`: the base answers it;
- `partial`: it answers part, and the gap is named;
- `insufficient`: the base does not know, and lore can offer external research;
- `conflicting`: sources disagree, and lore shows both;
- `stale`: the best source is marked as possibly outdated.

Only `verified` and `stale` documents answer. Drafts and archived ones never do.
