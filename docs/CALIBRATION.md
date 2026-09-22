# Calibração da busca (Fase 6)

Medido em 2026-09-22 no corpus de `tests/fixtures/corpus`
(8 docs, 12 perguntas de `tests/integration/test_search_eval.py`).

## Números

| Config | recall@3 | seção correta | latência |
| --- | --- | --- | --- |
| textual puro | 1.00 | 1.00 | 0.5ms/q |
| híbrido 0.9/0.1 (hash) | 1.00 | 0.90 | 5.8ms/q |
| híbrido 0.7/0.3 (hash) | 1.00 | 0.90 | 5.6ms/q |
| híbrido 0.5/0.5 (hash) | 1.00 | 0.90 | 5.6ms/q |
| híbrido 0.3/0.7 (hash) | 1.00 | 0.80 | 5.6ms/q |

Quanto mais peso semântico (hash), pior a seção: trigramas diluem o sinal
exato que o textual acerta.

## Decisão

- `retrieval.semantic = false` por padrão. Ganho do backend hash é zero
  (critério do plano: < 5pp em recall@3 mantém desligado).
- `HashEmbedder` fica como backend de teste/mecânica, não de produção.
- Ganho real depende de `EndpointEmbedder` com modelo local de verdade,
  ainda não medido aqui (nenhum modelo local nesta máquina).
- Pesos default mantidos em 0.7/0.3 para quando o endpoint existir;
  recalibrar então com este mesmo procedimento.
- Kill switch: `lore search --lexical` / `retrieval.semantic = false`
  volta ao textual puro, sem regressão (teste `test_kill_switch_*`).

## Como recalibrar

1. `lore reindex --semantic` com o backend novo;
2. rodar a grade de pesos sobre `QUERIES` do eval;
3. atualizar esta tabela e os defaults em `config.py`.
