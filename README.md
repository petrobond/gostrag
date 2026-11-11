# gostrag

RAG-система по российским стандартам в области искусственного интеллекта (ГОСТ Р / ПНСТ).
Отвечает на прицельные вопросы по корпусу стандартов, цитирует конкретный пункт и страницу,
проходит внутренний аудит соответствия ГОСТам с помощью LLM-as-a-judge (GigaChat).

## Ключевые решения

- **LLM:** GigaChat 3 Ultra (freemium) с fallback-цепочкой Max → Pro → Lite → DeepSeek.
- **Эмбеддинги:** локальные `intfloat/multilingual-e5-large` (FastEmbed, ONNX, 1024 dim).
  GigaChat embeddings требуют оплаты (HTTP 402), поэтому по умолчанию отключены.
- **Хранилища:** Qdrant (векторы), BM25 (разреженный индекс), PostgreSQL (метаданные, квоты, отчёты).
- **Доступ:** только Telegram-бот, whitelist пользователей.
- **Развёртывание:** локально в Docker Compose, затем перенос на VPS.

## Документы

- `plans/01-plan.md` — подробный план реализации.
- `plans/02-gost-compliance.md` — проверка плана на соответствие ГОСТам.
- `plans/03-gold-set.md` — контрольный набор 30 вопросов.
- `plans/04-decisions.md` — журнал архитектурных решений (ADR).
- `docs/` — артефакты ГОСТ-соответствия.

## Требования

- Python 3.12
- Docker + Docker Compose (Qdrant)
- Ключи: GigaChat (`secrets/gigachatAPI`), Telegram (`secrets/telegram`)

## Быстрый старт (локально)

```bash
# 1. окружение
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp deploy/.env.example deploy/.env   # заполнить секреты

# 2. зависимости
docker compose -f deploy/docker-compose.yml up -d qdrant

# 3. корпус: PDF → чанки
.venv/bin/python -m app.cli ingest --source data/source --out data/corpus

# 4. эмбеддинги + Qdrant + BM25
.venv/bin/python -m app.cli embed \
  --corpus data/corpus --index data/index \
  --qdrant-url http://localhost:6333

# 5. вопрос из CLI
.venv/bin/python scripts/ask.py "Что такое извлечение информации по ГОСТ Р 71476?"

# 6. Telegram-бот
.venv/bin/python -m bot.main

# 7. HTTP API
.venv/bin/uvicorn app.main:app --port 8000
```

## Проверка

```bash
.venv/bin/python -m pytest -q tests
.venv/bin/python scripts/test_gigachat.py
.venv/bin/python eval/judge.py --limit 5
```

## Аудит ГОСТ

```bash
.venv/bin/python scripts/extract_requirements.py eval/requirements.yaml 60
.venv/bin/python scripts/audit.py --user-id 478645956
```

Отчёт сохраняется в `reports/{version}/{user_id}/` и идемпотентен: повторный запуск
возвращает существующий отчёт. Manifest содержит версию, git commit, git tag и SHA-256.

## Бот

Telegram: **@pbondarev_gostrag_bot** (доступ по whitelist).

## Ссылки на источники

Каждая цитата в боте содержит ссылку на PDF в Object Storage с якорем страницы:

```
https://storage.yandexcloud.net/<bucket>/gost/ai_gost_1/<file>.pdf?...#page=N
```

Presigned URL действует 7 дней; объекты в бакете не изменяются.

## Результаты

| Метрика | Значение |
|---|---|
| Recall@6 | 1.000 (12/12) |
| Judge pass rate | 0.833 (25/30) |
| Faithfulness | 0.83 |
| Citation | 0.70 |
| Аудит ГОСТ: требований | 60 |
| Соответствует | 32 |
| Частично | 7 |
| Не соответствует | 1 |
| Не применимо | 20 |
| Compliance rate (от применимых) | 80% |

Подробнее — `docs/eval_results.md`, `eval/report.json`, `reports/0.1.0/478645956/audit.md`.

## Ограничения

- GigaChat freemium: 1 одновременный поток → очередь.
- GigaChat embeddings платные → локальные e5-large.
- 2 документа без нумерованных пунктов не проиндексированы (терминологические).
- Аудит внутренний, не является сертификацией.

## Структура

```
app/            приложение: ingest, rag, llm, guard, storage, audit
bot/            Telegram-бот (aiogram)
scripts/        CLI: ingest, ask, audit, диагностика
eval/           gold set, judge, requirements
docs/           артефакты ГОСТ-соответствия
plans/          план, проверка, ADR
deploy/         Dockerfile, compose, .env.example
db/             схема PostgreSQL
tests/          unit-тесты
```

Секреты хранятся в `secrets/` и в git не попадают.

