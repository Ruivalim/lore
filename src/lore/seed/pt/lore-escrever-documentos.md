---
id: lore-escrever-documentos
title: Escrever e importar documentos
summary: Crie com `lore new --type howto --title "Título"`, importe Markdown qualquer com `lore import arquivo.md`; todo documento tem front matter com id, title, type, status, tags, datas e sources.
type: reference
status: verified
reviewed_by: human
seed: 0.1.0
tags:
  - lore
  - documentos front-matter
created_at: 2026-11-05
updated_at: 2026-11-05
verified_at: 2026-11-05
review_after: 2027-05-05
sources:
  - url: https://github.com/Ruivalim/lore
    title: Lore, README e config.example.toml
    accessed_at: 2026-11-05
---

# Escrever e importar documentos

## Perguntas que este documento responde

Como crio um documento novo? Como importo uma nota que já tenho? Quais campos
o front matter precisa? Quais tipos existem? Como cito uma fonte?

## Criar e importar

```sh
lore new --type howto --title "Rotacionar chaves SSH"   # rascunho a partir do template
lore import nota.md     # o agente sugere título, tipo, tags e resumo
lore add nota.md        # arquivo que já tem front matter do Lore
```

Tudo nasce em `drafts/` e só responde depois de aprovado.

## Front matter

Obrigatórios: `id` (slug minúsculo), `title`, `type`, `status`, `tags`,
`created_at`, `updated_at` e `sources`. Em `verified`, também `verified_at`.
Opcionais: `summary` (a resposta curta, até 600 caracteres), `review_after`,
`supersedes` e `related`.

Tipos: `howto`, `troubleshooting`, `reference`, `concept`, `decision`,
`research` e `note`. Estados: `draft`, `verified`, `stale` e `archived`.

## Fontes

Cada item de `sources` é um destes:

- web: `url`, `title` e `accessed_at`;
- experiência própria: `kind: personal` e `description`;
- arquivo local: `kind: local`, `path` e `description`.

`sources` vazia só vale para `note`. Use lista em bloco (um item por linha,
com `-`); lista entre colchetes não é aceita.
