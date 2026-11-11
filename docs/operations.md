# Эксплуатация

## 1. Запуск

```bash
docker compose -f deploy/docker-compose.yml up -d qdrant
.venv/bin/python -m bot.main
```

Для API:

```bash
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 2. Обновление корпуса

```bash
# 1. Добавить PDF в data/source
# 2. Пересобрать чанки
.venv/bin/python -m app.cli ingest --source data/source --out data/corpus
# 3. Переиндексировать
.venv/bin/python -m app.cli embed --corpus data/corpus --index data/index \
  --qdrant-url http://localhost:6333
# 4. Удалить устаревшие точки
.venv/bin/python scripts/cleanup_qdrant.py
# 5. Обновить версию корпуса в deploy/.env
```

## 3. Проверка работоспособности

```bash
curl -s http://localhost:8000/health
.venv/bin/python scripts/eval_retrieval.py
.venv/bin/python -m pytest -q tests
```

## 4. Аудит ГОСТ

```bash
.venv/bin/python scripts/extract_requirements.py eval/requirements.yaml 60
.venv/bin/python scripts/audit.py --user-id 478645956
```

Отчёт: `reports/{version}/{user_id}/audit.md`, `audit.json`, `manifest.json`.

## 5. Лимиты и квоты

| Параметр | Значение | Где менять |
|---|---|---|
| Вопросов в час | 10 | `HOURLY_QUESTIONS_PER_USER` |
| Вопросов в день | 50 | `DAILY_QUESTIONS_PER_USER` |
| Токенов в день (глобально) | 2 000 000 | `DAILY_TOKENS_GLOBAL` |
| Top-K | 6 | `MAX_TOP_K` |
| Таймаут | 90 с | `REQUEST_TIMEOUT_SEC` |

## 6. Резервное копирование

- PostgreSQL: `pg_dump`.
- Qdrant: снимок volume `qdrant_storage`.
- Корпус: `data/corpus/*.jsonl`.
- Отчёты: `reports/`.

## 7. Мониторинг

- `/health` — статус и готовность индекса.
- Логи бота: stdout (Docker logs).
- Расход токенов: `GET /balance` (не работает при pay-as-you-go) или статистика в личном кабинете GigaChat.

## 8. Инциденты

| Симптом | Причина | Действие |
|---|---|---|
| 402 от GigaChat | кончились токены модели | fallback на следующую модель |
| 429 | 1 поток занят | очередь, retry, DeepSeek |
| 413 | промпт больше контекста | уменьшить top-K |
| Пустые ответы | индекс не готов | проверить `/health`, переиндексировать |
