---
id: lore-tui-shortcuts
title: TUI shortcuts
summary: In the TUI, `a` asks, `f` switches between the short and full answer, `v` filters drafts and verified documents, `A` approves, `R` rejects and `q` quits.
type: reference
status: verified
reviewed_by: human
seed: 0.1.0
tags:
  - lore
  - tui shortcuts
created_at: 2026-11-05
updated_at: 2026-11-05
verified_at: 2026-11-05
review_after: 2027-05-05
sources:
  - url: https://github.com/Ruivalim/lore
    title: Lore, README and config.example.toml
    accessed_at: 2026-11-05
---

# TUI shortcuts

## Questions this document answers

What are the TUI shortcuts? How do I see the full answer in the TUI? How do I
approve from the TUI? How do I cancel research?

## Shortcuts

| Key | What it does |
| --- | --- |
| `a` or `?` | focuses the question box; `enter` sends, `esc` goes back |
| `/` | filters the list |
| `v` | cycles between all, drafts and verified |
| `enter` | opens the selected document |
| `tab` | moves focus between list, reader and question |
| `d` | switches between the answer and the document |
| `f` | switches between the short and the full answer |
| `p` | researches the last question externally |
| `A` | approves a draft, confirms an auto-approved one or reactivates a stale one |
| `R` | rejects the draft, asking for the reason |
| `e` | edits in `$EDITOR` |
| `r` | reloads the list |
| `q` | quits |

Before research there is a countdown: `n` or `esc` cancels, `enter` starts
right away, any other key pauses it.

Single letter shortcuts only work outside the question box: after asking,
`esc` goes back to the list.
