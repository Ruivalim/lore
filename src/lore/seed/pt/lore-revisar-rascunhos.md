---
id: lore-revisar-rascunhos
title: Revisar, aprovar e rejeitar rascunhos
summary: `lore review` lista o que espera revisão; aprove com `lore approve <id> --human` e rejeite com `lore reject <id> --reason "motivo" --human`.
type: howto
status: verified
reviewed_by: human
seed: 0.1.0
tags:
  - lore
  - revisao rascunhos
created_at: 2026-11-05
updated_at: 2026-11-05
verified_at: 2026-11-05
review_after: 2027-05-05
sources:
  - url: https://github.com/Ruivalim/lore
    title: Lore, README e config.example.toml
    accessed_at: 2026-11-05
---

# Revisar, aprovar e rejeitar rascunhos

## Perguntas que este documento responde

Como aprovo um rascunho? Como rejeito um rascunho? Onde vejo o que falta
revisar? Dá para aprovar automaticamente? O que é `reviewed_by: auto`? Como
reativo um documento desatualizado (stale)?

## Procedimento

```sh
lore review                      # fila: rascunhos, stale, vencidos, aprovados sem revisão
lore review <id>                 # detalhe: trechos sem fonte e possíveis conflitos
lore edit <id>                   # abre no $EDITOR
lore approve <id> --human        # vira verified e vai para knowledge/
lore reject <id> --reason "motivo" --human   # vai para archive/ com o motivo
```

No TUI, `v` filtra os rascunhos, `A` aprova (pede confirmação), `R` rejeita
(pede o motivo) e `e` edita.

## Estados

`draft` vira `verified` ou `archived`. Um `verified` pode virar `stale`
(`lore stale <id> --human`), que ainda responde mas com aviso, e `verified` ou
`stale` podem ir para `archived` (`lore archive <id> --human`). Revisou um
`stale` e ele continua valendo? `lore approve <id> --human` reativa como
`verified` e empurra o `review_after` pelo mesmo intervalo de antes. Passou do
`review_after`, o documento aparece na fila como vencido.

## Aprovação automática

Em `[review]`, cada origem tem uma política:

```toml
[review]
import = "human"      # human | auto-if-clean | auto
research = "human"
```

`auto-if-clean` só aprova pesquisa com fonte web, sem trecho sem fonte, sem
página descartada por injection e sem conflito; no import, só olha conflito.
`auto` aprova qualquer rascunho válido. O que entra assim fica com
`reviewed_by: auto` e continua na fila até `lore approve <id> --human`
confirmar.
