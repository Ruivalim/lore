---
id: lore-configuring-agents
title: Configuring agents and models
summary: Pick the default agent and model in `[llm]`, override per task in `[llm.answer]`, `[llm.import]` or `[llm.research]`; presets are pi, claude, codex, agy and openai.
type: howto
status: verified
reviewed_by: human
seed: 0.1.0
tags:
  - lore
  - config agents
created_at: 2026-11-05
updated_at: 2026-11-05
verified_at: 2026-11-05
review_after: 2027-05-05
sources:
  - url: https://github.com/Ruivalim/lore
    title: Lore, README and config.example.toml
    accessed_at: 2026-11-05
---

# Configuring agents and models

## Questions this document answers

How do I change the model? How do I use Claude, Codex or agy? How do I use
another CLI? How do I use a local endpoint? How do I check the agent answers?

## Procedure

The default agent applies to every task:

```toml
[llm]
agent = "pi"
model = "provider/model-id"
```

Each task can override it: `[llm.answer]` (synthesis for `lore ask`),
`[llm.import]` (metadata for `lore import`) and `[llm.research]` (research).
The `[llm]` model is only inherited when the task uses the same agent.

```toml
[llm.research]
agent = "claude"
model = "claude-opus-5-5"
```

Presets: `pi`, `claude`, `codex`, `agy` and `openai` (an OpenAI-compatible
endpoint, with `endpoint` and `api_key_env` under `[agents.openai]`). Any
other CLI goes in `[agents.<name>]`:

```toml
[agents.my-cli]
command = ["my-cli", "--quiet", "{model_args}"]
model_args = ["--model", "{model}"]
prompt = "stdin"
error_patterns = ["^Error:"]
```

`error_patterns` is for CLIs that exit 0 even when they fail.

## Verification

`lore doctor` checks that each agent's binary exists; `lore doctor --probe`
calls each one with a minimal prompt. Every option is in lore's
`config.example.toml`, and the base's config lives in `.lore/config.toml`.
