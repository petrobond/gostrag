# Результаты оценки v3.2.2

| Поле | Значение |
|---|---|
| Gold v2 | `eval/gold_set_v2.yaml` (37, 12 типов) |
| Gold v3 | `eval/gold_set_v3.yaml` (50, 19 стандартов) |
| Gold-KB | `eval/gold_kb.yaml` (10: термины, outline, links, path) |
| Индекс | Qdrant `gost_chunks_bge_m3_v2` + BM25, BGE-M3 (1024d) |
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

## 2. Gold v3 (50, v3.2.0/v3.2.1)

| Метрика | Значение |
|---|---|
| Retrieval recall@8 | **1.000 (41/41)** |
| Pass rate | **1.000 (50/50)** |
| Faithfulness / relevancy | 0.96 / 0.96 |
| Citation | **1.0** |
| Citation recall | **1.000 (58/58)** |
| Провалы | нет; M04, X01, TB01, KB10 — pass |

## 3. Gold-KB (10, v3.2.1)

| Метрика | Значение |
|---|---|
| Pass rate | **1.000 (10/10)** |
| Citation | **1.0 (28/28)** |
| KB07 | «стандарты корпуса» → внутренняя ветка `71476`, п. 2 |
| KB10 | внешние ссылки `71562`: 4 стандарта, п. 2, с. 5 |

## 4. Что изменилось в v3.2.1

- KB07: «корпус» — внутренняя ветка графа, external-links больше не перехватывает;
- KB10: deterministic external links, citation п. 2;
- M04: факт-карточка 71484.2 п. 5.2 / 72663 п. 8.1;
- TB01: таблица 6.3 — 8 строк по PDF;
- citation enforcement: citation recall 1.000 на gold v3;
- KB/граф: термины, outline, `/kb`, `/term`, `/links`, 1-hop для cross_reference;
- reranker `bge-reranker-v2-m3`: A/B recall 1.000 → 0.740 — не используется;
- BM25-fallback при 502/503 Cloud.ru.

## 5. v3.2: TB01 и KB10

| Проверка | Результат |
|---|---|
| Корпус | 2026.11.13: 38 документов, 4734 чанка, 871 табличный, uuid5 4541 |
| TB01 | **pass 1.0**; 8 строк таблицы 6.3, строки 6.1/6.2 не попали; citation ПНСТ 844—2023, таблица 6.3, с. 8 |
| KB10 | **pass 1.0**; ровно 4 внешних стандарта; citation ГОСТ Р 71562—2024, п. 2, с. 5 |
| KB07 | **pass 1.0** (v3.2.1); citation ГОСТ Р 71540—2024, п. 2, с. 5 |
| Тесты | **89 passed**, ruff clean |
| Аудит v3.2 | 157 требований / 15 ГОСТов; N/A 15 (9.55%); coverage 90.45%; compliance applicable 74.65% |

## 6. v3.2.2: корпус 2026.11.13-r2

| Параметр | Значение |
|---|---|
| Документов | 38 |
| Clause-записей | 3134 |
| Чанков | 4657 (3759 clause + 860 table + 38 meta) |
| Уникальных `text_hash` | 4495 |
| 72664 `/kb` | 1/2/9/7/3 + A/B/C/ДА/ДБ; без разделов 0 и 6 |
| Retrieval | gold v3 **41/41**, gold v2 **28/28** |
| Gold v3 judge | **47/50 (0.94)**; E04/M04/CL02 — strict-judge outliers; C05 pass |
| Gold-KB | **10/10**, citation **1.0** |
| Тесты | **89 passed**, ruff clean |

Gold v3 / gold-KB после пересборки: см. отчёт `eval/report_v3_r2.json` и
`eval/report_kb_r2.json` (прогон на локальной коллекции `_v3`).
