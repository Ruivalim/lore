---
id: lore-pesquisa-externa
title: Pesquisa externa e privacidade
summary: Com `research.enabled = true`, pergunta que a base não cobre vira pesquisa: no modo web o Lore busca e o agente redige, no modo agent o próprio agente pesquisa; tudo vira rascunho.
type: concept
status: verified
reviewed_by: human
seed: 0.1.0
tags:
  - lore
  - pesquisa privacidade
created_at: 2026-11-05
updated_at: 2026-11-05
verified_at: 2026-11-05
review_after: 2027-05-05
sources:
  - url: https://github.com/Ruivalim/lore
    title: Lore, README e config.example.toml
    accessed_at: 2026-11-05
---

# Pesquisa externa e privacidade

## Perguntas que este documento responde

Como ligo a pesquisa na internet? Qual a diferença entre o modo web e o modo
agent? O que impede um segredo de sair da máquina? Como pesquisar sem
confirmação?

## Como funciona

A pesquisa só roda com `research.enabled = true` e quando a cobertura é
`insufficient` ou `partial`. Antes há uma contagem de `research.confirm_timeout`
segundos: `n` ou `esc` cancela, `enter` vai na hora. `--yes` pula a
confirmação; `research.require_confirmation = false` também.

Dois modos, em `research.mode`:

- `web`: o Lore busca (`research.search_provider`), baixa as páginas, bloqueia
  endereço privado e descarta página com cara de prompt injection; o agente de
  `[llm.research]` só redige;
- `agent`: o próprio agente pesquisa na web e na base (hoje só o `claude`),
  sem ferramenta de escrita e com teto de gasto em `research.max_budget_usd`.
  `research.extra_instructions` soma instruções suas ao prompt dele.

A resposta sai marcada como não verificada e o rascunho vai para `drafts/`,
com o resumo no campo `summary`.

## Privacidade

Segredo detectado na pergunta ou no contexto local bloqueia o envio; página
com segredo é descartada; no modo agent, segredo na resposta bloqueia o
rascunho. O import faz a mesma checagem antes de mandar a nota ao agente. Padrões a mais entram em `privacy.extra_patterns`. Nada sai da
máquina com a pesquisa desligada.
