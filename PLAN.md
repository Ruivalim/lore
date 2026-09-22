# lore: plano de implementação

Decisões de stack fechadas com o Rui em 2026-09-22. Spec em `README.md`.
Nenhum código escrito antes do aceite deste plano (README §22).

## 0. Decisões de stack (§21 da spec, resolvidas)

| Questão adiada | Decisão | Motivo |
| --- | --- | --- |
| Linguagem | Python >= 3.11 | Stdlib cobre sqlite3+FTS5, argparse, tomllib. Deps pequenas, testes locais simples. |
| Biblioteca de CLI | argparse (stdlib) | Superfície pequena (12 comandos). Zero dependência, sem lockfile na Fase 1. |
| Representação de embeddings | Nenhuma até a Fase 6 | Retrieval terá interface (`Scorer`) onde o lexical é um scorer. Semântico entra como segundo scorer, aditivo. |
| Modelo local padrão | Nenhum fixo; endpoint OpenAI-compatible configurável | Princípio 9: provedores substituíveis. Ausente vira modo extrativo. |
| Provedores remotos iniciais | Nenhum fixo; interface + config, implementação na Fase 4 | Evita amarrar acervo a fornecedor. |
| Busca web | Interface `WebSearch` + provedor configurável, Fase 4 | Mesmo motivo acima. |
| Fusão e reordenação | Fase 2: FTS5 + boosts por campo. Fusão híbrida só na Fase 6 | Calibrar com consultas reais antes de fundir (README §10.4). |
| Saída estruturada | `--json` com esquema estável por comando | Contrato testável desde a Fase 1. |
| Commits automáticos | Desligado por padrão, sempre explícito | README §17. Política `auto_commit = false` fixa na v1. |

Dependências externas na v1: nenhuma obrigatória. `pytest` só para dev.
Empacotamento: `pyproject.toml` com PEP 517 simples (`[build-system]` setuptools),
entry point `lore = lore.cli:main`. Sem lockfile enquanto só houver dev-deps;
reavaliar se entrar dependência runtime.

## 1. Layout do repositório

```text
lore/
├── README.md            # spec (fonte do produto)
├── PLAN.md              # este arquivo
├── pyproject.toml
├── src/
│   └── lore/
│       ├── __init__.py
│       ├── cli.py       # argparse, 12 comandos (§13)
│       ├── config.py    # carrega .lore/config.toml + env, valida
│       ├── models.py    # Doc, front matter, validação, transições de estado
│       ├── repo.py      # operações sobre Markdown (ler, criar, mover, escrita atômica)
│       ├── index.py     # FTS5: chunking por seção, indexação, rebuild
│       ├── retrieve.py  # busca textual + filtros + interface Scorer
│       ├── answer.py    # avaliador de cobertura + compositor extrativo (Fase 3)
│       ├── research.py  # pesquisador externo (Fase 4)
│       ├── review.py    # fila de revisão e promoção (Fase 5)
│       └── redact.py    # detecção e redação de segredos (§12.2)
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/        # corpus pequeno de docs + perguntas com docs esperados (§18.4)
├── knowledge/           # 5 categorias iniciais (§9), cada uma com .gitkeep
├── drafts/
├── archive/
├── templates/           # 1 modelo por tipo (§4), espelhando campos do §8
└── .lore/               # config.toml + index.sqlite (ignorado pelo git)
```

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
no corpus de fixture (máquina do Rui, número registrado no teste como referência,
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
  e pede decisão humana (README §12.2, §15).
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

## 3. Configuração (` .lore/config.toml`, criado por `lore config --init`)

```toml
[repository]
knowledge_dir = "knowledge"
drafts_dir = "drafts"
archive_dir = "archive"

[retrieval]
lexical = true
semantic = false        # Fase 6
# embedding_model = ""  # Fase 6

[answer]
mode = "local-first"
# local_model_endpoint = ""  # OpenAI-compatible; vazio = extrativo
allow_extractive_fallback = true

[research]
enabled = false         # Fase 4 liga o fluxo; provedor continua configurável
require_confirmation = true
# provider = ""
# web_search = ""

[privacy]
redact_secrets = true
send_full_documents = false
auto_commit = false     # sempre explícito na v1
```

## 4. Testes por nível (resumo do §18)

- Unidade: §18.1 completo desde a fase dona de cada componente.
- Integração: §18.2, com ciclo ponta a ponta na Fase 5.
- Segurança: §18.3 na Fase 4, mantidos como regressão.
- Recuperação: fixtures + métricas mínimas (§18.4) na Fase 2, recalibração na 6.
- Respostas: checklist do §18.5 aplicado a cada fixture de `ask` (fidelidade,
  cobertura, citação, incerteza, sem alegação solta, comando exato); autoridade
  final humana, sem LLM-juiz na v1.

## 5. Critérios de aceite da v1 (README §20, sem corte)

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
atualização curta do PLAN.md se algo desviou (motivo registrado).

## 7. Riscos e rollback

- FTS5 ausente no SQLite do sistema: fallback para ranking Python puro
  (documentado, mais lento, mesmos testes). Rollback: nenhum, degradação controlada.
- Escopo inchando (multiusuário, web, sync): fora de escopo (§5), recusar sem
  replanejar.
- Modelo local pesado: nunca obrigatório; extrativo é o modo padrão real.
- Cada fase é reversível por `git revert` do merge da fase; índice sempre
  reconstruível; Markdown canônico nunca depende de ferramenta.
