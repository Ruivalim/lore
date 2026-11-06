---
id: lore-configurar-agentes
title: Configurar agentes e modelos
summary: Em `[llm]` escolha agente e modelo padrão, e em `[llm.answer]`, `[llm.import]` ou `[llm.research]` troque por tarefa; presets: pi, claude, codex, agy e openai.
type: howto
status: verified
reviewed_by: human
seed: 0.1.0
tags:
  - lore
  - config agentes
created_at: 2026-11-05
updated_at: 2026-11-05
verified_at: 2026-11-05
review_after: 2027-05-05
sources:
  - url: https://github.com/Ruivalim/lore
    title: Lore, README e config.example.toml
    accessed_at: 2026-11-05
---

# Configurar agentes e modelos

## Perguntas que este documento responde

Como troco o modelo? Como uso o Claude, o Codex ou o agy? Como uso outro CLI?
Como uso um endpoint local? Como testo se o agente responde?

## Procedimento

O agente padrão vale para todas as tarefas:

```toml
[llm]
agent = "pi"
model = "provider/model-id"
```

Cada tarefa pode trocar: `[llm.answer]` (síntese do `lore ask`),
`[llm.import]` (metadados do `lore import`) e `[llm.research]` (pesquisa).
O `model` do `[llm]` só é herdado quando a tarefa usa o mesmo agente.

```toml
[llm.research]
agent = "claude"
model = "claude-opus-5-5"
```

Presets: `pi`, `claude`, `codex`, `agy` e `openai` (endpoint
OpenAI-compatível, com `endpoint` e `api_key_env` em `[agents.openai]`).
Qualquer outro CLI entra em `[agents.<nome>]`:

```toml
[agents.meu-cli]
command = ["meu-cli", "--quiet", "{model_args}"]
model_args = ["--model", "{model}"]
prompt = "stdin"
error_patterns = ["^Error:"]
```

`error_patterns` serve para CLI que sai com código 0 mesmo quando falha.

## Como verificar

`lore doctor` confere se o binário de cada agente existe; `lore doctor --probe`
chama cada um com um prompt mínimo. Todas as opções estão no
`config.example.toml` do Lore, e a config do acervo fica em `.lore/config.toml`.
