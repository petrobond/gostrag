# План v2: от текущего состояния к целевым метрикам

| Поле | Значение |
|---|---|
| Версия | 2.0.0 |
| Дата | 2026-11-11 |
| База | v1: pass rate 0.833, recall@6 1.0 |
| Golden set | `eval/gold_set_v2.yaml` (37 вопросов, 12 типов) |

---

## 1. Исследования

### 1.1 Типизация вопросов

| Источник | Вклад |
|---|---|
| MultiHop-RAG — https://arxiv.org/abs/2401.15391 | Типы: inference, comparison, temporal, null |
| Typed-RAG — https://arxiv.org/abs/2503.15879 | Типизация нефактоидных вопросов, type-aware декомпозиция |
| TRIAD — https://arxiv.org/abs/2608.21558 | Single-hop, multi-hop, binary; генерация датасета |
| StratRAG — https://arxiv.org/abs/2604.22757 | Bridge, comparison, yes-no |
| Обзор оценки — https://arxiv.org/abs/2504.14891 | Метрики citation precision/recall, faithfulness |

**Принятая типизация для ГОСТов:**

| Тип | Пример | Стратегия |
|---|---|---|
| definition | «дай определение компонента ИИ» | exact lookup по термину |
| clause_lookup | «что говорится в п. 8.3.4» | exact lookup по ГОСТ/пункту |
| enumeration | «какие слои/этапы» | parent expansion раздела |
| comparison | «чем отличаются A и B» | multi-hop: два retrieval + synthesis |
| table | «какие показатели в таблице» | поиск по табличным чанкам |
| appendix | «что в приложении ДА» | фильтр по приложению |
| cross_reference | «на какой ГОСТ ссылается» | поиск по ссылкам |
| binary | «обязателен ли» | поиск + проверка модальности |
| temporal | «когда введён» | поиск по датам |
| null_query | «какой ГОСТ регулирует RAG» | отказ |
| injection | «игнорируй инструкции» | классификатор + отказ |
| paraphrase | переформулировка | устойчивость |

### 1.2 Метрики

| Источник | Вклад |
|---|---|
| RAG Evaluation Survey — https://arxiv.org/abs/2504.14891 | Faithfulness, answer relevance, citation |
| SN Computer Science (2026) | Context relevance, correctness, citation quality |
| Cited but Not Verified — https://arxiv.org/abs/2605.06635 | Проверка атрибуции цитат |
| How Do LLMs Cite? — https://arxiv.org/abs/2606.28358 | Механика цитирования |
| Attribution Survey — https://arxiv.org/abs/2508.15396 | Citation precision/recall |

### 1.3 Защита от injection

| Источник | Вклад |
|---|---|
| nokast-secureRAG — https://arxiv.org/abs/2610.28364 | Малые модели как semantic firewall |
| RAG-PIBench — https://arxiv.org/abs/2610.08571 | Бенчмарк и типы атак |
| Layered Security — https://arxiv.org/abs/2606.19660 | Трёхуровневая защита |

---

## 2. Структура корпуса и влияние на ingest

| Особенность | Количество | Решение |
|---|---|---|
| Определения терминов | 151 | чанки с MIN_CHARS=40 (исправлено) |
| Таблицы | 132 | отдельные чанки с markdown-таблицами |
| Приложения | 72 | секция `Приложение X`, фильтр |
| Примечания | 314 | сохранять в чанке пункта |
| Перечисления | 170 | сохранять маркеры `а)`, `1)` |
| Cross-references | 55 | извлекать ссылки на ГОСТы |
| Разделы без пунктов | 608 | чанки разделов (исправлено) |

**Вывод:** текущий ingest покрывает определения, пункты и разделы; таблицы и cross-refs требуют доработки.

---

## 3. Целевые метрики

| Метрика | Baseline v1 | Цель v2 | Приоритет |
|---|---|---|---|
| Definition accuracy | — | ≥ 0.95 | Высокий |
| Clause lookup accuracy | — | ≥ 0.95 | Высокий |
| Enumeration completeness | — | ≥ 0.85 | Высокий |
| Comparison accuracy | — | ≥ 0.80 | Высокий |
| Table accuracy | — | ≥ 0.75 | Средний |
| Appendix accuracy | — | ≥ 0.80 | Средний |
| Citation precision | 0.70 | ≥ 0.95 | Высокий |
| Citation recall | — | ≥ 0.90 | Высокий |
| Faithfulness | 0.83 | ≥ 0.90 | Высокий |
| Answer correctness | — | ≥ 0.85 | Высокий |
| Refusal accuracy | 0.73 | ≥ 0.90 | Высокий |
| Injection resistance | 0.75 | ≥ 0.95 | Высокий |
| Paraphrase consistency | — | ≥ 0.90 | Средний |
| p95 latency | — | ≤ 20 с | Средний |
| Cost | — | ≤ 2 000 ₽/мес | Низкий |

---

## 4. Мероприятия

| № | Мероприятие | Закрывает | Оценка |
|---|---|---|---|
| 1 | Переиндексация с MIN_CHARS=40 и чанками разделов | definition, enumeration | 15 мин |
| 2 | Query classifier (правила + Lite) | все типы | 1 день |
| 3 | Multi-hop для comparison | comparison | 1 день |
| 4 | Injection classifier перед генерацией | injection | 1 день |
| 5 | Ссылки на PDF с #page | citation | готово |
| 6 | Табличные чанки (markdown) | table | 1 день |
| 7 | Golden set v2 + baseline | все | 2 часа |
| 8 | Повторная оценка и отчёт | все | 2 часа |

---

## 5. Этапы

| Этап | Содержание | Критерий |
|---|---|---|
| 0 | Переиндексация | 3209 чанков в Qdrant |
| 1 | Baseline v2 | отчёт по 37 вопросам |
| 2 | Query classifier | точность классификации ≥ 0.90 |
| 3 | Multi-hop | comparison ≥ 0.80 |
| 4 | Injection classifier | resistance ≥ 0.95 |
| 5 | Таблицы | table ≥ 0.75 |
| 6 | Финальная оценка | все цели достигнуты |
| 7 | Документация и коммит | отчёт + ADR |

---

## 6. Ограничения

- GigaChat 1 поток → multi-hop удваивает задержку.
- Таблицы в PDF извлекаются как текст; нужен отдельный парсер.
- Judge склонен строго оценивать сравнения.
- Целевые метрики требуют повторной калибровки на 20 примерах.

---

## 7. Прогресс v2.1 (release/v2.0.0)

### 7.1 Исправленные дефекты

| № | Дефект | Файл | Эффект |
|---|---|---|---|
| 1 | Dense-поиск отбрасывался: `DenseHit.chunk_id` = UUID точки Qdrant, а не `chunk_id` из payload | `app/storage/qdrant.py` | dense-хиты больше не теряются |
| 2 | Multi-hop перетирал переданный ГОСТ первым упоминанием в вопросе | `app/rag/retriever.py` | M01/M02/M04 видят оба документа |
| 3 | Multi-hop depth 3 → 4 + область применения каждого документа | `app/rag/retriever.py` | сравнения получают контекст обоих стандартов |
| 4 | Enumeration не раскрывал группу пунктов | `app/rag/retriever.py`, `app/rag/chunk_store.py` | E02: 6.1–6.6, E04: 4.1–4.7 |
| 5 | Comparison с одним ГОСТом не делился на сущности | `app/rag/retriever.py` | M05: 5.3.4 + 5.7.3 |
| 6 | Цитаты не нормализовались («пункт 5.3.4, страница 19») | `app/rag/generator.py` | citation precision |
| 7 | Clause lookup галлюцинировал при верном контексте | `app/rag/service.py` | extractive-ответ по пункту |
| 8 | Нет даты введения в индексе | `app/ingest/chunk.py` | meta-чанк на документ |
| 9 | Таблицы сплющивались в строку | `app/ingest/extract.py`, `app/ingest/parse.py`, `app/ingest/chunk.py` | pdfplumber + PyMuPDF fallback, 330 table-чанков |
| 10 | Judge считал citation=0 при отказах | `eval/judge.py` | n/a вместо 0 |
| 11 | Enumeration обрезал группу пунктов по cap 14 | `app/rag/retriever.py` | 4.6 и 8.3.3–8.3.6 попадают в контекст |
| 12 | Якорь перечисления выбирался по счётчику BM25 | `app/rag/retriever.py` | якорь по dense-сходству, вопрос без номера ГОСТа не уходит в случайный документ |
| 13 | Глубокие подпункты вытесняли заголовки слоёв | `app/rag/retriever.py` | мелкие пункты первыми (8.3.3, 8.3.5, 8.3.6) |

### 7.2 Результаты

| Прогон | Pass rate | definition | clause_lookup | enumeration | comparison | table | binary | temporal |
|---|---|---|---|---|---|---|---|---|
| baseline v2 | 0.676 | 6/6 | 4/5 | 3/5 | 0/5 | 1/2 | 0/1 | 0/1 |
| после P0+P1 | 0.757 | 6/6 | 3/5 | 4/5 | 2/5 | 1/2 | 0/1 | 1/1 |
| **финал (переиндексация + таблицы + meta)** | **0.973 (36/37)** | 6/6 | 5/5 | 5/5 | 4/5 | 2/2 | 1/1 | 1/1 |

Итоговые метрики judge: faithfulness 0.919, relevancy 0.919, citation 0.906, refusal 0.973.
Recall@8 = 1.000 (18/18). Не прошёл только M04 — см. `docs/eval_results_v2.md`.
