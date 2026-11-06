# lore: plano de implementação

Decisões de stack fechadas em 2026-09-22. Spec em `docs/spec.md`.

## 0. Decisões de stack (§21 da spec, resolvidas)

| Questão adiada | Decisão | Motivo |
| --- | --- | --- |
| Linguagem | Python >= 3.11 | Stdlib cobre sqlite3+FTS5, argparse, tomllib. Deps pequenas, testes locais simples. |
| Biblioteca de CLI | argparse (stdlib) | Superfície pequena (12 comandos). Zero dependência, sem lockfile na Fase 1. |
| Representação de embeddings | Nenhuma até a Fase 6 | Retrieval terá interface (`Scorer`) onde o lexical é um scorer. Semântico entra como segundo scorer, aditivo. |
| Backend de texto | Agente por tarefa (`[llm]`): presets Pi, Claude Code, Codex, agy, OpenAI-compatível, ou CLI próprio, sempre sem ferramentas nem sessão | Reusa logins e providers que o usuário já tem. Sem agente disponível, resposta extrativa permanece. |
| Provedores remotos iniciais | Nenhum fixo; interface + config, implementação na Fase 4 | Evita amarrar acervo a fornecedor. |
| Busca web | Interface `WebSearch` + provedor configurável, Fase 4 | Mesmo motivo acima. |
| Fusão e reordenação | Fase 2: FTS5 + boosts por campo. Fusão híbrida só na Fase 6 | Calibrar com consultas reais antes de fundir (spec §10.4). |
| Saída estruturada | `--json` com esquema estável por comando | Contrato testável desde a Fase 1. |
| Commits automáticos | Desligado por padrão, `[git] auto_commit` liga | spec §17. Commit dos arquivos tocados e push se houver upstream; nunca pull nem force. |

Dependências externas na v1: nenhuma obrigatória. `pytest` só para dev.
Empacotamento: `pyproject.toml` com PEP 517 simples (`[build-system]` setuptools),
entry point `lore = lore.cli:main`. Sem lockfile enquanto só houver dev-deps;
reavaliar se entrar dependência runtime.

## 1. Layout do repositório

```text
lore/
├── README.md
├── LICENSE
├── pyproject.toml
├── Makefile             # make help lista os alvos
├── docs/                # spec, plano, calibração
├── examples/acervo/     # acervo de exemplo para testar sem base própria
├── scripts/lore-sync.sh # pull --rebase + reindex + push, sob o lock do auto-commit
├── src/lore/
│   ├── cli.py           # argparse, todos os comandos
│   ├── config.py        # YAML global + TOML do acervo, defaults do exemplo
│   ├── config.example.toml
│   ├── agents.py        # agentes de texto (presets e CLI próprio)
│   ├── models.py        # front matter, validação, transições
│   ├── repo.py          # Markdown: ler, criar, mover, escrita atômica, init
│   ├── index.py         # FTS5: chunking por seção, indexação, rebuild
│   ├── retrieve.py      # busca textual, híbrida e interface Scorer
│   ├── semantic.py      # embeddings (hash local ou endpoint)
│   ├── answer.py        # cobertura, extrativo, síntese curta e completa
│   ├── research.py      # pesquisa web ou por agente, rascunho
│   ├── claude_cli.py    # Claude Code headless como pesquisador
│   ├── review.py        # fila, aprovação humana e política automática
│   ├── importer.py      # import com metadados do agente
│   ├── gitops.py        # auto-commit e lock
│   ├── redact.py        # detecção de segredos
│   └── templates/       # 1 modelo por tipo
├── tests/
└── tui/                 # lore-tui em Go (Bubble Tea)
```

O acervo (`knowledge/`, `drafts/`, `archive/`, `.lore/`) mora em repositório próprio, criado com `lore init`.

## 2. Fases

### Fase 1: núcleo documental (sem índice, sem rede)

Arquivos: `models.py`, `repo.py`, `config.py`, `cli.py` (só `new`, `add`, `show`, `doctor`),
`templates/*.md` (7 tipos), `pyproject.toml`.

- Esquema de front matter em `models.py`: campos do §8.1 obrigatórios,
  §8.2 condicionais (`verified_at` exigido se `status == verified`;
  `sources` vazia só aceita com `kind: personal` ou `type: note` com justificativa
  explícita? Não: spec diz vazia somente se experiência/nota pessoal. Regra:
  `sources == []` exige `type == note` ou entrada `kind: personal`).
  Datas ISO 8601 (`YYYY-MM-DD`). `id` slug único, case-insensitive.
- Máquina de estados com transições do §7; qualquer transição para `verified`
  exige flag `--human` (prova de aprovação humana no CLI; modelos chamam mesma
  função sem a flag e recebem erro).
- `repo.py`: escrita atômica (tmp + fsync + rename), detecção de id duplicado,
  `add` copia arquivo externo para `drafts/` ou `knowledge/` conforme status,
  nunca move original sem `--move`. Rejeita symlink que escape do repo,
  caminho absoluto fora da árvore, `..` traversal.
- `doctor`: config, docs inválidos (com motivo por arquivo), ids duplicados,
  links internos quebrados (`[[id]]` e `[x](<id>.md)`), fontes ausentes,
  vencidos (`review_after < hoje`), índice fora de sincronia (stub: reporta
  "índice ainda não existe" até a Fase 2).
- Comandos com `--json` desde o dia um.

Testes unidade: front matter válido/inválido (tabela de casos), cada transição
permitida e cada proibida, id duplicado, escrita atômica (mata processo no meio,
sem parcial), YAML malformado, Markdown malformado.

Concluída quando: `new` cria de cada template, `add` importa e valida,
`show` exibe, `doctor` lista erro por arquivo, `--json` válido, cobertura de
`models.py` + `repo.py` >= 90%.

### Fase 2: busca local textual

Arquivos: `index.py`, `retrieve.py`, `cli.py` (`search`, `reindex`).

- Chunking por seção: unidade = (doc_id, heading, nível, corpo, posição).
  Indexa título, tags, headings, corpo, blocos de código (com marcador
  `is_code` para boost de comando exato). Nunca indexa `draft` nem `archived`
  como fonte confiável (filtro padrão `status in (verified, stale)`; `stale`
  carrega aviso).
- FTS5 com BM25 + boosts: título x4, tags x3, heading x2, código x2 em match
  exato, corpo x1. Tokenizer `unicode61` com `remove_diacritics 1` (português
  sem acento casa com acentuado).
- `search` mostra por resultado: arquivo, seção, por que casou
  (textual/título/tag/código), status do doc. `--json` com mesmos campos.
- `reindex` apaga e reconstrói só de Markdown; determinístico (mesmo corpus
  resulta em mesmo índice, ordem de inserção por `id`).
- Corpus de avaliação em `tests/fixtures/`: 10 a 15 docs curtos + 20 perguntas
  com doc e seção esperados. Métricas do §18.4 viram teste de regressão
  (recall@3 do doc correto, seção correta).

Concluída quando: importar, indexar, achar funciona; `reindex` após `rm .lore/index.sqlite`
restaura; avaliação de recuperação roda em `pytest` e passa; latência p50 local < 200ms
no corpus de fixture (máquina de desenvolvimento, número registrado no teste como referência,
não como teto rígido).

### Fase 3: consulta fundamentada (`ask` extrativo + síntese local opcional)

Arquivos: `answer.py`, `cli.py` (`ask`).

- Classificação de cobertura (§10.5): `sufficient | partial | insufficient |
  conflicting | stale`. Regra determinística v1, auditável, sem modelo:
  conta chunks relevantes (score >= limiar calibrado no corpus), verifica se
  todos os componentes da pergunta têm ao menos um chunk (componentes =
  substantivos/termos extraídos por heurística simples, documentada), marca
  `conflicting` se dois docs `verified` discordam (heurística: chunks com
  negação explícita sobre mesmo termo; conservadora, prefere falso negativo),
  `stale` se melhor fonte é `stale`.
- Modo extrativo (padrão, sem modelo): devolve top chunks com contexto +
  citações `arquivo#seção`. Nunca sintetiza frase nova além de cola neutra
  ("Segundo X..."). Comandos e valores copiados byte a byte.
- Síntese local: chamada só ao endpoint configurado; prompt monta só com
  pergunta + chunks selecionados; resposta validada (toda afirmação precisa
  de citação incluída, verificada por pós-checagem simples de spans citados;
  falha na validação cai para extrativo com aviso).
- `ask` nunca consulta `draft`/`archived` como confiável; `stale` só com aviso
  visível. Cobertura `partial`/`insufficient` imprime lacuna nomeada e pergunta
  sobre fallback externo somente se Fase 4 existir e política permitir;
  com `--local-only` nunca pergunta.
- Opções do §13.1 desde o início: `--local-only`, `--extractive`, `--type`,
  `--tag`, `--as-of`, `--json`, `--yes` (`--yes` sem provedor configurado = erro,
  não silently local).

Testes: pergunta conhecida responde com citação exata; pergunta desconhecida
recusada sem invenção (resposta contém marcador de ausência + zero afirmações);
parcial nomeia lacuna; offline funciona (sem socket: teste com rede bloqueada);
`--as-of` exclui docs posteriores; comandos preservados byte a byte.

Concluída quando: matriz de cobertura (5 classes x fixtures) passa;
nenhuma resposta sem citação; modo sem modelo é o padrão e funciona.

### Fase 4: pesquisa externa e rascunhos

Arquivos: `research.py`, `redact.py`, `cli.py` (fallback do `ask`).

- Gate de confirmação: `partial`/`insufficient` sugere pesquisa, pede `[S/n]`
  salvo `--yes` com política ok. Antes de qualquer envio: mostra o que vai
  (pergunta + chunks listados), roda `redact.py`; segredo detectado bloqueia
  e pede decisão humana (spec §12.2, §15).
- `redact.py`: regex para tokens/chaves/senhas/cookies/URLs com credencial +
  lista configurável `privacy.extra_patterns`. recall > precisão: dúvida bloqueia.
- Ordem de fontes do §10.6; cada fonte registra URL, título, `accessed_at`.
  Distingue citação de conclusão do modelo no rascunho (seções separadas).
- Prompt injection: conteúdo web entra como `dados`, nunca como instrução;
  pós-checagem proíbe no rascunho gerado: mudança de `status` para `verified`,
  blocos de comando fora de seção marcada, instruções ao sistema
  ("ignore", "execute", "altere"). Achou, descarta trecho e registra.
- Rascunho válido em `drafts/` (passa na validação da Fase 1, `status: draft`,
  `verified_at: null`), resposta marcada "externa, ainda não verificada".
  Pesquisa inconclusiva gera rascunho com incerteza explícita ou nada, sempre
  explicando.

Testes segurança (§18.3): página com injeção não altera regras nem promove
rascunho; segredo em pergunta/doc bloqueia envio (mock de transporte que falha
o teste se chamado); fonte maliciosa não muda política; doc remoto gigante
truncado com aviso; caminhos fora do repo rejeitados.

Concluída quando: ciclo pergunta desconhecida -> autoriza -> rascunho válido
com fontes + resposta marcada; todos os testes de segurança passam; sem
config de provedor o comando explica em vez de quebrar.

### Fase 5: revisão e promoção

Arquivos: `review.py`, `cli.py` (`review`, `approve`, `reject`, `archive`, `stale`).

- `review` (sem id) lista fila: drafts + vencidos + stale, ordenados por
  `updated_at`. `review <id>` mostra conteúdo proposto, fontes com datas,
  alegações sem fonte (frases sem citação, detectadas pela mesma pós-checagem
  da Fase 3), conflitos com docs existentes (overlap de tags + termos com
  veredito divergente), diff contra versão anterior (`supersedes` ou mesmo `id`).
- Ações: aprovar (só com `--human`; move para `knowledge/`, seta `verified_at`,
  reindexa), editar (abre `$EDITOR`, revalida), rejeitar (motivo obrigatório,
  vai para `archive/` com `status: archived`?), nova pesquisa (volta para Fase 4),
  manter rascunho, arquivar. `approve` sem `--human` = erro.
- Reindex automático após promoção; pergunta equivalente respondida localmente
  (teste de ciclo completo do §20, item 8).

Concluída quando: ciclo completo do §20 demonstrável de ponta a ponta
(itens 1 a 10) em script de integração; nenhuma promoção sem `--human`.

### Fase 6: busca semântica e calibração

Arquivos: `retrieve.py` (segundo scorer), `index.py` (store de vetores em
SQLite, tabela separada, igualmente descartável), doc de calibração.

- Embeddings locais configuráveis (`retrieval.embedding_model`), store apagável
  junto com `reindex --full`. Fusão: soma ponderada lexical + semântico com
  pesos calibrados no corpus de avaliação (grid simples, pesos registrados em
  config + doc). Kill switch: `retrieval.semantic = false` volta ao Fase 2 puro.
- Medição: roda avaliação do §18.4 antes e depois; documenta delta
  (recall@k, latência). Se ganho < 5pp em recall@3, recomendação é manter
  desligado por padrão.
- Recalibra limiares do avaliador de cobertura com dados reais.

Concluída quando: relatório de calibração escrito; semântica desligável;
nenhuma regressão na avaliação textual pura.

## 3. Configuração

`src/lore/config.example.toml` tem todas as opções com o valor padrão; é a fonte dos defaults e o template de `lore init`. O YAML global (`~/.config/lore/config.yaml`) aceita as mesmas chaves e é lido antes; o TOML do acervo ganha, menos `repository.root`.

## 4. Testes por nível (resumo do §18)

- Unidade: §18.1 completo desde a fase dona de cada componente.
- Integração: §18.2, com ciclo ponta a ponta na Fase 5.
- Segurança: §18.3 na Fase 4, mantidos como regressão.
- Recuperação: fixtures + métricas mínimas (§18.4) na Fase 2, recalibração na 6.
- Respostas: checklist do §18.5 aplicado a cada fixture de `ask` (fidelidade,
  cobertura, citação, incerteza, sem alegação solta, comando exato); autoridade
  final humana, sem LLM-juiz na v1.

## 5. Critérios de aceite da v1 (spec §20, sem corte)

Os 10 itens do ciclo + 5 obrigatórios valem integralmente. Demonstração por
script `tests/integration/test_learning_cycle.py` que executa os 10 passos em
repo temporário. Falha em qualquer item reprova a release.

## 6. Ordem de execução e marcos

1. Fase 1 -> milestone `fase-1-nucleo` (branch + tag, sem push sem autorização).
2. Fase 2 -> `fase-2-busca`.
3. Fase 3 -> `fase-3-ask`.
4. Fase 4 -> `fase-4-pesquisa`.
5. Fase 5 -> `fase-5-revisao` + demo do ciclo §20.
6. Fase 6 -> `v0.1.0` com relatório de calibração.

Cada fase termina com: testes verdes, `lore doctor` limpo no próprio repo,
atualização curta deste plano se algo desviou (motivo registrado).

## 7. Riscos e rollback

- FTS5 ausente no SQLite do sistema: fallback para ranking Python puro
  (documentado, mais lento, mesmos testes). Rollback: nenhum, degradação controlada.
- Escopo inchando (multiusuário, web, sync): fora de escopo (§5), recusar sem
  replanejar.
- Modelo local pesado: nunca obrigatório; extrativo é o modo padrão real.
- Cada fase é reversível por `git revert` do merge da fase; índice sempre
  reconstruível; Markdown canônico nunca depende de ferramenta.

## 8. Desvios registrados na implementação (v0.1.0)

- Ranking textual usa score próprio (cobertura de termos por coluna com
  saturação log), não BM25: BM25 punia a seção longa que casava mais
  (medido no eval) e `offsets()` FTS5 falha neste SQLite; contagem via
  `highlight()` por coluna.
- MATCH usa OR entre termos (stopwords pt + len<3 removidos): AND recusava
  pergunta real por causa de flexão/stopword.
- `approve`/`reject`/`archive`/`stale` exigem `--human` no CLI.
- `sources: []` só com `type: note`; doctor avisa sem sources nos demais.
- Calibração Fase 6: backend hash com ganho zero, semântica off por padrão
  (ver `docs/CALIBRATION.md`).
- Revisão de completude: `lore edit <id>` expõe no CLI o fluxo `$EDITOR` que já existia no módulo de revisão.
- Geração de texto passa pelo agente da tarefa (`[llm.answer]`, `[llm.import]`, `[llm.research]`), sem sessão, ferramentas ou contexto de projeto; embeddings continuam no endpoint configurado.
- `lore import` usa o agente só para metadados e resumo; corpo fica preservado e o arquivo nasce draft, salvo política em `[review] import`. Origem local é registrada como `sources.kind: local`.
- Config global em `~/.config/lore/config.yaml` define `repository.root` e o agente padrão; raiz resolve por `--root`, ancestral do diretório atual e então config global. TOML do acervo sobrescreve opções operacionais, nunca a raiz.
- Resposta curta por padrão e completa com `--full`; documentos ganham `summary` opcional, gerado no import e na pesquisa.
- `[review]` permite aprovação automática por origem; aprovado sem revisão fica `reviewed_by: auto` até confirmação humana.
- Fallback externo respeita `require_confirmation = false`, funciona em `--json`, envia trechos locais na cobertura parcial e cria IDs exclusivos para pesquisas repetidas.
- O ciclo CLI completo de pesquisa, draft, aprovação humana e reutilização local vive em `tests/integration/test_learning_cycle.py`.
- `make install` usa pipx em modo editável para expor `lore` no PATH do usuário.
- Segurança: pesquisa aceita somente HTTP(S) com resolução pública; bloqueia destinos privados e redirects para rede local para reduzir SSRF.
