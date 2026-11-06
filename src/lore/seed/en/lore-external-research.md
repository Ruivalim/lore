---
id: lore-external-research
title: External research and privacy
summary: With `research.enabled = true`, questions the base cannot answer become research: in web mode lore searches and the agent writes, in agent mode the agent researches on its own; the result is always a draft.
type: concept
status: verified
reviewed_by: human
seed: 0.1.0
tags:
  - lore
  - research privacy
created_at: 2026-11-05
updated_at: 2026-11-05
verified_at: 2026-11-05
review_after: 2027-05-05
sources:
  - url: https://github.com/Ruivalim/lore
    title: Lore, README and config.example.toml
    accessed_at: 2026-11-05
---

# External research and privacy

## Questions this document answers

How do I turn on web research? What is the difference between web and agent
mode? What keeps a secret from leaving the machine? How do I research
without confirming?

## How it works

Research only runs with `research.enabled = true` and when coverage is
`insufficient` or `partial`. A countdown of `research.confirm_timeout`
seconds comes first: `n` or `esc` cancels, `enter` starts right away.
`--yes` skips the confirmation, and so does
`research.require_confirmation = false`.

Two modes, in `research.mode`:

- `web`: lore searches (`research.search_provider`), fetches the pages, blocks
  private addresses and drops pages that look like prompt injection; the
  `[llm.research]` agent only writes;
- `agent`: the agent researches the web and the base on its own (only `claude`
  today), without write tools and with a spending cap in
  `research.max_budget_usd`. `research.extra_instructions` adds your own
  instructions to its prompt.

The answer comes back marked as unverified and the draft goes to `drafts/`,
with the short answer in its `summary`.

## Privacy

A secret detected in the question or the local context blocks sending; a page
with a secret is dropped; in agent mode a secret in the answer blocks the
draft. Imports run the same check before the note reaches the agent. Extra
patterns go in `privacy.extra_patterns`. Nothing leaves the machine while
research is off.
