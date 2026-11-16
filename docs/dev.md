# Локальная разработка

## 1. Контур

Разработка, ingest, embed, eval, judge и audit выполняются локально.
VPS `ultra` — только runtime (без VS Code Server, сборок и ingest).

| Компонент | Адрес |
|---|---|
| API | `http://127.0.0.1:8000` |
| Qdrant | `http://127.0.0.1:6335` |
| PostgreSQL | `127.0.0.1:5432` |
| Redis | `127.0.0.1:6379` |

Порт Qdrant `6335` выбран потому, что `6333` занят старым локальным
контейнером `gostrag-qdrant-1`.

## 2. Первый запуск

```bash
make dev-up            # qdrant/postgres/redis в Docker
make seed-qdrant       # восстановить snapshot прода (4452 точки)
make api               # uvicorn на 127.0.0.1:8000
```

Проверка:

```bash
curl -s http://127.0.0.1:8000/health
curl -s -X POST http://127.0.0.1:8000/api/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"Что такое искусственный интеллект?","top_k":3}'
```

## 3. Переменные

`deploy/.env` — локальный файл (gitignored, 600). В нём:
- `QDRANT_URL=http://localhost:6335`;
- `QDRANT_COLLECTION=gost_chunks_bge_m3_v3` (локальный контейнер; `_v2` — rollback);
- `EMBEDDING_PROVIDER=cloudru`;
- `DATA_*`, `INDEX_DIR`, `REPORTS_DIR` — абсолютные локальные пути;
- ключи Cloud.ru/GigaChat/DeepSeek/S3 — из `secrets/`, не печатать.

`Makefile` дополнительно экспортирует те же значения для скриптов.

## 3.1. Локальные эмбеддинги (fallback)

Базовый образ и по умолчанию `EMBEDDING_PROVIDER=cloudru` не содержат
`fastembed`/ONNX. Для локального fallback:

```bash
.venv/bin/pip install -e '.[local]'
EMBEDDING_PROVIDER=local make api
```

В Docker: `--build-arg INSTALL_LOCAL_EMBEDDINGS=true`.

## 4. Тесты и оценка

```bash
make test
make lint
make eval-retrieval
make judge
```

## 5. Бот

Локальный бот с прод-токеном **не запускать** — один poller на проде.
Для локальных e2e использовать `TELEGRAM_TEST_BOT_TOKEN` из `secrets/telegram`
и отдельный профиль запуска (не коммитить токен).

## 6. Бэкапы

Перед ingest/reindex:

```bash
mkdir -p backups/$(date +%F)
tar -czf backups/$(date +%F)/data-local.tar.gz data/corpus data/index data/kb
```

Qdrant snapshot:

```bash
.venv/bin/python scripts/qdrant_snapshot.py download \
  --url http://localhost:6335 --collection gost_chunks_bge_m3_v3 \
  --out backups/$(date +%F)/qdrant.snapshot
```

## 7. Веб-интерфейс (v3.3.0)

```bash
make dev-up
make api            # WEB_COOKIE_SECURE=false, http://127.0.0.1:8000
```

Создать локального администратора и открыть `/login`:

```bash
.venv/bin/python -m app.cli web-user create \
  --email admin@example.ru --role admin --password-stdin
```

Тесты:

```bash
.venv/bin/python -m pytest -q tests
TEST_POSTGRES_DSN='postgresql://gostrag:gostrag@127.0.0.1:5432/gostrag' \
  .venv/bin/python -m pytest -q tests/test_web_store_pg.py
```

Особенности:

- локально `WEB_COOKIE_SECURE=false` (иначе `Secure`-cookie не уходит по HTTP);
- миграции `web_*` применяются автоматически на старте (`WEB_AUTOMIGRATE=true`);
- без PostgreSQL приложение поднимается в деградированном режиме
  (`/health` → `web_ready: false`);
- шаблоны и статика — `app/web/templates`, `app/web/static` (htmx закоммичен,
  npm не нужен).
