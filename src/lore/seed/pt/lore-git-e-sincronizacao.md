---
id: lore-git-e-sincronizacao
title: Acervo no Git e sincronização
summary: `lore init <caminho>` cria o acervo com git; com `git.auto_commit = true` cada mudança vira commit e push automático se a branch tiver upstream.
type: howto
status: verified
reviewed_by: human
seed: 0.1.0
tags:
  - lore
  - git sincronizacao
created_at: 2026-11-05
updated_at: 2026-11-05
verified_at: 2026-11-05
review_after: 2027-05-05
sources:
  - url: https://github.com/Ruivalim/lore
    title: Lore, README e config.example.toml
    accessed_at: 2026-11-05
---

# Acervo no Git e sincronização

## Perguntas que este documento responde

Como crio um acervo novo? Como faço o Lore commitar sozinho? Como sincronizo
entre máquinas? Por que o doctor diz que há commit não enviado?

## Procedimento

```sh
lore init ~/notas          # knowledge/, drafts/, archive/, .lore/ e git init
```

Fora do acervo, o Lore usa `repository.root` do `~/.config/lore/config.yaml`.
Dentro dele, acha a raiz sozinho; `--root` força outra.

Com `git.auto_commit = true`, cada comando que muda arquivo faz commit só do
que tocou e push se a branch tiver upstream. O Lore nunca faz pull, rebase nem
force push. Para escrever de mais de uma máquina, o script `lore-sync` do
repositório do Lore faz pull com rebase, reindexa e envia, sob o mesmo lock.

Push que falhou fica pendente e o `lore doctor` avisa quantos commits faltam
subir.

## Índice

O índice em `.lore/index.sqlite` é descartável: `lore reindex` reconstrói a
partir dos arquivos. `.lore/` fica fora do Git.
