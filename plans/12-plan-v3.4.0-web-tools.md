# План v3.4.0: веб-инструменты и команды

| Поле | Значение |
|---|---|
| Версия | 3.4.0 |
| Дата | 2026-11-17 |
| Ветка | `release/v3.0.0` |
| Основание | решения владельца 2026-11-17: страницы + палитра, admin-only команды, аудит read-only |

## Решения

1. Справочные команды дублируются **страницами `/tools/*`**, а не большими
   текстовыми ответами в чате.
2. В чате добавляются slash-команды и командная палитра для быстрого перехода.
3. `/tools/*` доступны авторизованным пользователям; admin-команды — только admin.
4. `/stats` объединяет веб-метрики (`web_*`) и данные бота (`qa_log`/`usage_daily`).
5. `/audit` и `/audit_status` — **read-only**: список отчётов и статус manifest,
   запуск аудита из веба не добавляется.
6. Версия — `v3.4.0`.

## Маршруты

| Telegram | Веб |
|---|---|
| `/start`, `/help` | `/help` |
| `/gosts` | `/tools/gosts` |
| `/ask` | `/chat` / `/web/ask` |
| `/kb <ГОСТ>` | `/tools/gosts/{gost}?tab=outline` |
| `/term <термин>` | `/tools/terms?q=...` |
| `/links <ГОСТ>` | `/tools/gosts/{gost}?tab=links` |
| `/stats` | `/admin` (admin) |
| `/audit` | `/admin/audit` (admin, read-only) |
| `/audit_status` | `/admin/audit#status` (admin, read-only) |

## Реализация

- `app/web/tool_data.py` — read-only адаптеры документов, KB, TermCatalog, S3;
- `app/web/routes_tools.py` — `/tools/*`, `/help`;
- `app/web/commands.py` — единый список команд и parser;
- `app/web/routes_chat.py` — slash-команды до RAG/LLM;
- `app/web/templates/tools/*`, `help.html`, command palette в `base.html`;
- `app/web/static/app.js`, `app.css` — палитра, mobile nav;
- `app/web/routes_admin.py` — статус manifest;
- `app/web/routes_api.py` + `app/main.py` — UsageStore и объединённая статистика.

## Приёмка

- `/tools/gosts` — 37 стандартов;
- `/tools/gosts/71476` — разделы, 105 терминов, связи;
- `/tools/terms?q=...` — поиск;
- `/help` — публичные команды; admin видит admin-команды;
- `/stats` user → 403, admin → статистика;
- `/admin/audit` — статус и отчёты, без запуска;
- старые web-тесты, auth, chat, CSRF не ломаются;
- `pytest` ≥ 176 passed, ruff clean.

## Не-цели

- запуск аудита из веба;
- загрузка/ингест документов;
- публичная регистрация;
- изменения RAG, Qdrant, BM25, промптов;
- миграции БД и переиндексация.

## Результат

Реализовано и задеплоено в v3.4.0: `/tools/gosts`, `/tools/gosts/{gost}`,
`/tools/terms`, `/help`, command palette, slash-команды, объединённая статистика
и read-only статус аудита. Проверено на проде; smoke-пользователь удалён.
