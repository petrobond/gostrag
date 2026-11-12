# Результаты оценки v3.1

| Поле | Значение |
|---|---|
| Gold v2 | `eval/gold_set_v2.yaml` (37, 12 типов) |
| Gold v3 | `eval/gold_set_v3.yaml` (50, 19 стандартов) |
| Gold-KB | `eval/gold_kb.yaml` (10: термины, outline, links, path) |
| Индекс | Qdrant `gost_chunks_bge_m3` + BM25, BGE-M3 (1024d) |
| KB | 400 терминов, 97 узлов, 116 рёбер (24 внутренних) |

## 1. Gold v2 (37)

| Метрика | Значение |
|---|---|
| Pass rate | **0.973 (36/37)** |
| Faithfulness / relevancy | 0.919 / 0.919 |
| Citation | 0.963 |
| Citation recall | **1.000 (54/54)** |
| Refusal | 0.973 |
| Recall@8 | **1.000 (28/28)** |

## 2. Gold v3 (50)

| Метрика | Значение |
|---|---|
| Retrieval recall@8 | **1.000 (41/41)** |
| Pass rate | **0.98 (49/50)** |
| Faithfulness / relevancy | 0.96 / 0.98 |
| Citation | 0.951 |
| Citation recall | **1.000 (64/64)** |
| Провал | TB01 (таблица 6.3: добавлены строки) |

## 3. Gold-KB (10)

| Метрика | Значение |
|---|---|
| Pass rate | **0.90 (9/10)** |
| Провал | KB10 (внешние ссылки) |

## 4. Что изменилось в v3.1

- E02: title-aware anchor + фильтр этапов;
- T01: слияние дублей `chunk_id` `#8.2` (Acc-I-1…7);
- citation enforcement: fallback-цитата, citation recall 1.000;
- M04: факт-карточка 71484.2 п. 5.2 / 72663 п. 8.1, точечный judge pass 1.0;
- KB/граф: термины, outline, `/kb`, `/term`, `/links`, 1-hop для cross_reference;
- reranker `bge-reranker-v2-m3`: A/B recall 1.000 → 0.740 — не используется;
- BM25-fallback при 502/503 Cloud.ru.

Ограничение: gold-KB KB10 (внешние ссылки) — известный провал; gold v3 финальный
прогон выполняется после включения KB и M04.
