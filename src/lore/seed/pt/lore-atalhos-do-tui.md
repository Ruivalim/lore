---
id: lore-atalhos-do-tui
title: Atalhos do TUI
summary: No TUI, `a` pergunta, `f` alterna resposta curta e completa, `v` filtra rascunhos e verificados, `A` aprova, `R` rejeita e `q` sai.
type: reference
status: verified
reviewed_by: human
seed: 0.1.0
tags:
  - lore
  - tui atalhos
created_at: 2026-11-05
updated_at: 2026-11-05
verified_at: 2026-11-05
review_after: 2027-05-05
sources:
  - url: https://github.com/Ruivalim/lore
    title: Lore, README e config.example.toml
    accessed_at: 2026-11-05
---

# Atalhos do TUI

## Perguntas que este documento responde

Quais são os atalhos do TUI? Como vejo a resposta completa no TUI? Como aprovo
pelo TUI? Como cancelo a pesquisa?

## Atalhos

| Tecla | O que faz |
| --- | --- |
| `a` ou `?` | foca a caixa de pergunta; `enter` envia, `esc` volta |
| `/` | filtra a lista |
| `v` | alterna entre todos, rascunhos e verificados |
| `enter` | abre o documento selecionado |
| `tab` | troca o foco entre lista, leitor e pergunta |
| `d` | alterna entre a resposta e o documento |
| `f` | alterna entre a resposta curta e a completa |
| `p` | pesquisa externamente a última pergunta |
| `A` | aprova o rascunho, confirma um aprovado sem revisão ou reativa um stale |
| `R` | rejeita o rascunho, pedindo o motivo |
| `e` | edita no `$EDITOR` |
| `r` | recarrega a lista |
| `q` | sai |

Antes de pesquisar há uma contagem: `n` ou `esc` cancela, `enter` vai na hora,
outra tecla pausa.

Os atalhos de uma letra só funcionam fora da caixa de pergunta: depois de
perguntar, `esc` volta para a lista.
