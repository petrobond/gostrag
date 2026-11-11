# Результаты оценки v2

| Поле | Значение |
|---|---|
| Golden set | `eval/gold_set_v2.yaml` (37 вопросов, 12 типов) |
| Корпус | 3209 чанков |
| Дата | 2026-11-11 |

## 1. Retrieval

Заполняется после `scripts/eval_retrieval.py --gold eval/gold_set_v2.yaml`.

## 2. Judge по категориям

Заполняется после `eval/judge.py --gold eval/gold_set_v2.yaml`.

| Категория | Вопросов | Pass rate | Цель |
|---|---|---|---|
| definition | 6 | — | ≥ 0.95 |
| clause_lookup | 5 | — | ≥ 0.95 |
| enumeration | 5 | — | ≥ 0.85 |
| comparison | 5 | — | ≥ 0.80 |
| table | 2 | — | ≥ 0.75 |
| appendix | 1 | — | ≥ 0.80 |
| cross_reference | 1 | — | ≥ 0.80 |
| binary | 1 | — | ≥ 0.85 |
| temporal | 1 | — | ≥ 0.85 |
| null | 4 | — | ≥ 0.90 |
| injection | 4 | — | ≥ 0.95 |
| paraphrase | 2 | — | ≥ 0.90 |

## 3. Изменения относительно v1

| Изменение | Причина |
|---|---|
| MIN_CHARS 120 → 40 | короткие определения терялись |
| Чанки разделов | раздел 1 не попадал в индекс |
| Query classifier | разные типы вопросов требуют разных стратегий |
| Multi-hop retrieval | сравнения двух ГОСТов |
| Injection guard | отказ без вызова LLM |
| S3-ссылки с #page | переход к цитате в PDF |
