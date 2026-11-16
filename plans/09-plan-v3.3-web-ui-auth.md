# План v3.3: веб-интерфейс и авторизация

| Поле | Значение |
|---|---|
| Версия плана | 3.3.0 |
| Дата | 2026-11-16 |
| Ветка | `release/v3.0.0` |
| Репозиторий | `git@github.com:petrobond/gostrag.git` |
| Прод | VPS `ultra` (45.15.252.185), `/opt/gostrag` |
| Основание | задание «лёгкий веб-интерфейс и авторизация», ответы владельца 1–6 (2026-11-16) |
| ADR | `docs/adr/001-web-ui-auth.md` |

## Решения владельца (2026-11-16)

| № | Вопрос | Решение |
|---|---|---|
| 1 | Домен / TLS | доступ по IP возможен только по HTTPS; для пилота — бесплатный DNS + Let's Encrypt, для постоянной работы — свой домен; порты 80/443 открыть |
| 2 | Механизм входа | email + пароль; веб не использует Telegram |
| 3 | Регистрация | только по приглашению/администратору; admin-аккаунт `bondarev-petr@yandex.ru` создаётся на первом деплое |
| 4 | Админ-панель | да: статистика, пользователи, документы (read-only), отчёты аудита (read-only) |
| 5 | Права на pharma-rag | подтверждены; всё равно используем только UX-паттерны, код пишем свой |
| 6 | Версия релиза | `v3.3.0` |

Подтверждено владельцем 2026-11-16: блокировка `/api/ask` и `/health` снаружи,
admin-роль только через CLI, приглашения/reset вручную (без SMTP),
TTL сессии 7 дней / idle 24 ч, лимиты логина 10/IP и 5/email за 15 минут.

## Отклонение от предыдущего плана

В веб-контуре «владелец» определяется ролью `web_users.role='admin'`, а не
`TELEGRAM_ADMIN_IDS`: владелец запретил использовать Telegram в вебе.
`TELEGRAM_ADMIN_IDS` остаётся только для бота. Отклонение согласовано
ответами №2 и №3.

## Этапы

### Этап 0. ADR и план

- `docs/adr/001-web-ui-auth.md`, `plans/09-plan-v3.3-web-ui-auth.md`.
- Коммит: `docs(plan): add v3.3 web ui auth plan and adr`.

### Этап 1. Auth backend

- `app/web/{security,store,migrations,auth,ratelimit,templating,forms}.py`;
- `app/web/routes_pages.py` (`/`, `/login`, `/logout`, `/invite/{token}`, `/password`),
  `app/web/routes_api.py` (`/me`);
- `app/main.py`: `create_app()`, пул PostgreSQL, автомиграции, `StaticFiles`,
  `web_ready` в `/health`;
- `app/cli.py`: `web-user create|list|passwd|invite`, `db migrate`;
- зависимости: `jinja2`, `argon2-cffi`;
- шаблоны `base/login/invite/password/errors`, `static/app.css`, `static/app.js`;
- тесты: `test_web_security.py`, `test_web_auth.py`, `test_web_store_pg.py`.

### Этап 2. Веб-чат

- `app/web/chat.py`, `/chat`, `/chat/{id}`, `/web/ask`, `/web/conversations/*`,
  `/api/web/conversations*`, `/api/web/ask`;
- цитаты с S3-ссылками `#page=N`, отказы, ошибки LLM/Qdrant, лимиты и семафор;
- шаблоны `chat.html`, `partials/*`;
- тесты: `test_web_chat.py`.

### Этап 3. Админка

- `/admin`, `/admin/users`, `/admin/documents`, `/admin/audit`,
  `/api/web/admin/stats`;
- статистика: вопросы, отказы, активные пользователи, p50/p95, версия корпуса;
- пользователи: список, приглашение, блокировка, reset-ссылка;
- read-only документы и отчёты аудита (whitelist путей);
- тесты: `test_web_admin.py`.

### Этап 4. Инфраструктура и приёмка

- `deploy/Caddyfile`, сервис `proxy` в compose, `.env.example`, deploy-скрипт,
  `scripts/smoke_web.sh`;
- CI: PostgreSQL-сервис для интеграционных тестов;
- версия `3.3.0` (`pyproject.toml`, `app/config.py`, `deploy/Dockerfile`,
  `deploy/.env.example`, `Makefile`);
- документация: `docs/web.md`, `docs/releases/v3.3.0.md`, `README.md`,
  `AGENTS.md`, `docs/operations.md`, `docs/cicd.md`, `docs/dev.md`,
  `docs/networking.md`;
- замеры `docker stats` до/после → `docs/reports/3.3.0/resources.md`.

## Критерии приёмки

- `pytest -q tests` — все тесты, включая auth/API/RBAC;
- `ruff check app bot eval tests` — clean;
- гость → redirect на `/login`; чужие диалоги → 404; user на admin → 403;
- cookie `HttpOnly`, `Secure`, `SameSite`; CSRF проверяется; logout инвалидирует сессию;
- в ответе цитата и рабочая ссылка на PDF с `#page=N`;
- ошибка LLM/Qdrant не роняет процесс;
- `docker stats` — доп. ≤150 MiB RAM, статика ≤5 MiB, swap не растёт;
- бот и его тесты не сломаны; `/health` не раскрывает секреты.

## Ресурсный бюджет

| Компонент | RAM | Диск |
|---|---|---|
| `app` (Jinja2, шаблоны, asyncpg pool) | +20–40 MiB | +~2 МБ образ |
| `proxy` (Caddy 2) | +25–40 MiB | ~60 МБ образ |
| PostgreSQL (6 таблиц) | +5–10 MiB | ~1–2 МБ |
| **Итого** | **~50–90 MiB** | статика ~70 KiB |
