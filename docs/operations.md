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
# 3. Переиндексировать (локально Qdrant на 6335; на VPS — 6333)
.venv/bin/python -m app.cli embed --corpus data/corpus --index data/index \
  --qdrant-url http://localhost:6335
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

## 9. VPS: очистка 2026-11-13

VPS `ultra` переведён в режим **runtime-only**: без VS Code Server, сборок,
ingest и правок кода. Разработка — только локально.

| Параметр | До | После |
|---|---|---|
| Диск `/` | 19 ГБ / 49 ГБ (41%) | 14 ГБ / 49 ГБ (30%) |
| Docker build cache | 4.894 ГБ | 0 |
| `~/.vscode-server` | 803 МБ | удалён |
| `curlimages/curl` | 35.9 МБ | удалён |
| `ProBack_SA` | active | active |
| gostrag | 5 сервисов healthy | 5 сервисов healthy |

Не трогать: `ProBack_SA` (`proback-rag-bot.service`), AWG `awg0`,
`deploy/.env`, volumes `gostrag_*`. VS Code Server на VPS не возвращать.
Проверка после очистки:

```bash
ssh ultra 'df -h /; free -h; sudo docker system df; systemctl is-active proback-rag-bot'
curl -s localhost:8000/health
```

## 10. Веб-интерфейс (v3.3.0)

- Публичный вход: `https://$WEB_DOMAIN` (Caddy, профиль `proxy`), приложение
  остаётся на `127.0.0.1:8000`.
- Порты: открыть TCP 80/443 (ufw + панель провайдера). Qdrant, PostgreSQL и
  Redis не публикуются.
- Переменные в `deploy/.env`: `WEB_DOMAIN` и `WEB_*` (шаблон —
  `deploy/.env.example`). Без `WEB_DOMAIN` proxy не запускается.
- `/api/ask` и `/health` снаружи закрыты (404), доступны только с VPS.

Первый администратор:

```bash
cd /opt/gostrag
sudo docker compose -f deploy/docker-compose.yml --env-file deploy/.env \
  run --rm app python -m app.cli web-user create \
  --email bondarev-petr@yandex.ru --role admin
```

Проверка:

```bash
curl -s localhost:8000/health | python -m json.tool   # web_ready: true
curl -s -o /dev/null -w '%{http_code}\n' "https://$WEB_DOMAIN/login"          # 200
curl -s -o /dev/null -w '%{http_code}\n' "https://$WEB_DOMAIN/api/ask"        # 404
bash scripts/smoke_web.sh http://127.0.0.1:8000
```

Пользователи: `/admin/users` (приглашение, блокировка, сброс пароля).
SMTP нет — ссылки передаются вручную и одноразовы.

Бэкап веб-таблиц входит в общий `pg_dump` деплой-скрипта. Откат на `v3.2.4`
безопасен: старый образ не использует таблицы `web_*`.

Подробно: `docs/web.md`.

