---
id: lore-como-perguntar
title: Como perguntar ao Lore
summary: Use `lore ask "pergunta"` para a resposta curta com fonte, e `--full` para a completa; sem pergunta, `lore ask` abre o TUI.
type: howto
status: verified
reviewed_by: human
seed: 0.1.0
tags:
  - lore
  - ask busca
created_at: 2026-11-05
updated_at: 2026-11-05
verified_at: 2026-11-05
review_after: 2027-05-05
sources:
  - url: https://github.com/Ruivalim/lore
    title: Lore, README e config.example.toml
    accessed_at: 2026-11-05
---

# Como perguntar ao Lore

## Perguntas que este documento responde

Como faço uma pergunta? Como vejo a resposta completa? O que quer dizer a
cobertura? Como buscar sem modelo? Como pesquisar só na base local?

## Procedimento

Pergunte em linguagem natural:

```sh
lore ask "como vejo os assuntos dos últimos commits"
```

A saída é a resposta curta, de uma a três frases, com a fonte no formato
`arquivo#seção`. Para a resposta completa, use `--full`. Sem pergunta,
`lore ask` abre o TUI.

Opções úteis:

- `--extractive`: não chama modelo nenhum, mostra os trechos encontrados;
- `--local-only`: nunca pesquisa fora da base;
- `--type howto` e `--tag git`: filtram os documentos usados;
- `--as-of 2026-01-01`: ignora documentos atualizados depois da data;
- `--json`: saída estruturada, com a curta em `short` e a completa em `text`.

Para ver os trechos sem resposta montada, use `lore search "termos"`.

## Cobertura

Toda resposta diz quanto a base cobriu a pergunta:

- `sufficient`: a base responde;
- `partial`: responde uma parte, e a lacuna aparece na resposta;
- `insufficient`: a base não sabe, e o Lore pode oferecer pesquisa externa;
- `conflicting`: as fontes discordam, e o Lore mostra as duas;
- `stale`: a melhor fonte está marcada como desatualizada.

Só documentos `verified` e `stale` respondem. Rascunho e arquivado nunca.
