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

## Decisão (revista com embeddings reais em 2026-09-22)

Backend: `endpoint` com `bge-m3:567m-fp16` via Ollama (`/v1`).
Chat/síntese: `qwen3:4b-instruct-2507-q4_K_M` via Ollama (`/v1`).

| Config | recall@3 | seção correta | latência |
| --- | --- | --- | --- |
| textual puro | 1.00 | 1.00 | 1ms/q |
| híbrido-bge 0.9/0.1 | 1.00 | 0.90 | 45ms/q |
| híbrido-bge 0.7/0.3 | 1.00 | 0.90 | 43ms/q |
| híbrido-bge 0.5/0.5 | 1.00 | 0.90 | 42ms/q |
| híbrido-bge 0.3/0.7 | 1.00 | 0.90 | 42ms/q |

No corpus pequeno o textual já é perfeito, então a fusão não soma.
O valor aparece em paráfrase sem termo em comum:

| Pergunta | textual | híbrido-bge |
| --- | --- | --- |
| fazer cópia de segurança do servidor | partial (doc errado) | partial com restic-x99 no topo |
| descansar melhor sem estimulante | insufficient | partial com sono-cafeina no topo |
| asdf qwerty zxcv (lixo) | insufficient | insufficient (floor segura) |

Dois bugs achados e corrigidos nessa medição:

- híbrido retornava vazio quando o textual não casava (matava justo o
  caso semântico puro); agora completa com achados só-semânticos.
- cobertura ignorava evidência semântica; agora conta como `partial`
  com lacuna declarada, nunca `sufficient` silencioso.
- `sem_floor = 0.45`: achado só-semântico abaixo disso é descartado
  (relevantes medidos em 0.49-0.52, lixo em 0.44, query fora do
  domínio em ~0.30). Margem fina: recalibrar no acervo real.

Recomendação atual: `semantic = true` com backend endpoint, pesos
0.7/0.3, floor 0.45. `--lexical` continua como kill switch.

## Como recalibrar

1. `lore reindex --semantic` com o backend novo;
2. rodar a grade de pesos sobre `QUERIES` do eval;
3. atualizar esta tabela e os defaults em `config.py`.
