# План v3.3.3: adaptive retrieval и LLM-поднаборы терминов

| Поле | Значение |
|---|---|
| Версия | 3.3.3 |
| Дата | 2026-11-17 |
| Ветка | `release/v3.0.0` |
| Основание | нестабильный ответ по «ГОСТе Р 71476», семантический поднабор терминов, решения владельца 2026-11-17 |
| Предыдущий план | `plans/10-plan-v3.3.1-rag-answers.md` |

## Решение

Не строить исчерпывающую таксономию интентов. Вместо этого — **bounded adaptive
planner + инструменты + LLM-listwise selector + verifier**:

1. fast-path для точных закрытых запросов (пункт, таблица, inventory);
2. planner для запросов, которым нужен инструмент/критерий;
3. LLM выбирает подмножество терминов, но только из каталога;
4. verifier проверяет цитаты и членство терминов;
5. fallback на обычный RAG, если данных/уверенности нет.

Это соответствует направлению Agentic RAG и set-level selection, но без
RL-обучения, open-web и полного GraphRAG — для 39 PDF это избыточно.

## Эмпирическая причина

Запрос «Какие основные термины определены в ГОСТе Р 71476?»:

- `ГОСТе` не распознавался regex: нужен был номинативный `ГОСТ Р`;
- `extract_gosts()` возвращал `[]`;
- вопрос классифицировался как `enumeration`;
- top-k заполнялся другими стандартами, где сказано «применены термины по
  ГОСТ Р 71476»;
- LLM либо отказывался, либо достраивал ответ из параметрической памяти.

Для корректной формы `ГОСТ Р 71476` exact-фильтр уже работает, но при вопросе
«характеризуют ИИ-систему как целое» находит раздел 7 (обзор системы), а не
пункты 3.x.y. Поэтому одного intent/фильтра недостаточно.

В корпусе 71476: **105 определений** в 7 подразделах (3.1–3.7), а
`data/kb/terms.jsonl` содержит только 5 заголовков подразделов — это не каталог
терминов. Каталог строится из `chunks.jsonl`.

## Исследовательская база

| Работа | Идея | Что берём |
|---|---|---|
| Agentic RAG survey, arXiv:2501.09136 | planning, tool use, reflection вместо статического workflow | bounded planner/tools |
| DeepResearcher, arXiv:2504.03160 | plan → search → verify → reflect; честный отказ | цикл проверки и отказа, без RL |
| Adaptive-RAG, arXiv:2403.14403 | выбор стратегии по сложности запроса | fast-path vs planner |
| GraphRAG, arXiv:2404.16130 | глобальные вопросы требуют графа/community summaries | иерархия терминов и разделов |
| RAPTOR, arXiv:2401.18059 | recursive summaries для holistic-вопросов | section/term summaries при необходимости |
| PACMS, arXiv:2606.20047 | submodular context selection | выбирать множество, а не top-k |
| BoundaryMORPH, arXiv:2609.27213 | set membership для diffuse retrieval | variable-size subset |
| RankGPT, arXiv:2304.09542 | LLM listwise reranking | LLM выбирает термины из кандидатов |
| RAG Compositionality, arXiv:2610.29722 | компоненты не складываются автоматически | end-to-end A/B, без слепого стека |
| DeepResearch RewardBench, arXiv:2611.10156 | LLM-judge и рубрики для deep research | оценка поднаборов и траекторий |

Свежие препринты 2026 (PACMS, BoundaryMORPH, LASAGNA) — источник идей, не
готовая production-библиотека. Полный GraphRAG/RAPTOR/RL откладывается до
подтверждения пользы на нашем eval.

## Архитектура

```text
fast path: clause/table/inventory/definition
        │ не применим
        ▼
adaptive planner (JSON, max 4 steps)
        │
        ├── resolve_reference
        ├── search_corpus
        ├── list_terms
        ├── rank_terms
        ├── select_terms (LLM listwise)
        └── get_definition / outline
        ▼
verifier: термин ∈ каталог, цитата ∈ чанк, ГОСТ совпадает
        ▼
answer / conservative refusal
```

MVP v3.3.3 реализует:

- `app/rag/gost_refs.py` — морфология ГОСТов и единый regex;
- `app/rag/term_catalog.py` — 105 терминов 71476, группировка 3.1–3.7;
- `app/rag/term_selector.py` — embedding-кандидаты + LLM selection;
- `app/rag/adaptive.py` — bounded planner для term inventory/subset;
- `app/rag/service.py` — маршрутизация, citations, fallback;
- fast-path сохраняется для точных пунктов, таблиц, inventory.

Полный открытый planner для любых вопросов — следующий инкремент, если eval
покажет пользу. Сейчас planner не пытается угадать все интенты: он вызывает
инструменты только там, где они дают проверяемый результат.

## Потоки

### Полный инвентарь

```text
«Какие основные термины определены в ГОСТе Р 71476?»
→ resolve_reference → ГОСТ Р 71476—2024
→ list_terms → 105 терминов
→ deterministic inventory, 7 section citations, 0 LLM
```

### Семантический поднабор

```text
«Какие термины ГОСТа Р 71476 характеризуют ИИ-систему как целое?»
→ resolve_reference → ГОСТ Р 71476—2024
→ rank_terms (embedding по name + definition) → 25 кандидатов
→ select_terms (LLM listwise по рубрике) → 5–8 терминов
→ verifier: clause ∈ каталог, citation ∈ чанк
→ точные определения + citations
```

### Конкретное определение

```text
«Что такое агент ИИ по ГОСТе Р 71476?»
→ definition fast-path → find_term(exact_gost)
→ точное определение 3.1.1
```

### Fallback

- нет каталога/терминов → обычный RAG;
- LLM selector вернул пусто/невалидное → top semantic candidates с пометкой;
- planner/embedding/LLM упал → fast-path/RAG, без 500;
- нет цитат → refusal, а не ответ из памяти модели.

## Не-цели

- RL-обучение (DeepResearcher/Search-R1);
- open-web поиск;
- полный GraphRAG с LLM-графом;
- RAPTOR-дерево для всего корпуса;
- замена существующего reranker (A/B ранее ухудшил recall);
- переиндексация Qdrant и миграции БД.

## Этапы

| Этап | Содержание | Статус |
|---|---|---|
| 1 | морфология ГОСТов, тесты падежей | сделано |
| 2 | TermCatalog из chunks, inventory, citations | сделано |
| 3 | embedding-кандидаты + LLM selector + verifier | сделано |
| 4 | adaptive planner и fallback в AskService | сделано |
| 5 | pytest/ruff, gold v2/v3, judge, ручные вопросы | сделано (167 passed; judge 47/50) |
| 6 | docs, версия, тег, deploy, smoke | сделано (v3.3.3 в проде) |

## Приёмка

- `Какие основные термины определены в ГОСТе Р 71476?` — **105 терминов,
  7 цитат, без LLM, без чужих ГОСТов**.
- `Какие термины ГОСТа Р 71476 характеризуют ИИ-систему как целое?` —
  5–8 терминов, все `gost=71476`, все citations валидны, нет ответа из
  параметрической памяти.
- `Что такое агент ИИ по ГОСТе Р 71476?` — 3.1.1.
- Негативные: «какие требования определены…» не должно уходить в term inventory;
  «какие ГОСТы…» остаётся corpus inventory; неизвестный ГОСТ — RAG/refusal.
- `pytest`: все тесты; `ruff` clean.
- gold v2/v3 retrieval: не ниже 0.973/1.000; judge — не хуже baseline
  (с учётом известных strict-outliers).
- Ручная проверка `/api/ask`, веб-чата и бота после деплоя.

## Риски

- Семантический критерий «как целое» субъективен; нужен рубрика/eval.
- LLM selector может быть нестабилен; кандидаты и цитаты ограничивают его.
- Дополнительный LLM-вызов добавляет 2–8 с; inventory остаётся 0 мс.
- PACMS/BoundaryMORPH/GraphRAG — исследовательские идеи, не внедряются
  без A/B на нашем корпусе.
- При росте корпуса каталог и section citations строятся из данных, не хардкодятся.

## Rollback

- planner можно отключить feature-флагом/возвратом к fast-path;
- каталог терминов не меняет Qdrant/BM25;
- откат образа на v3.3.2 без миграций и переиндексации.

