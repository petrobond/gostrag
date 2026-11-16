# ADR 001: веб-интерфейс и авторизация gostrag

| Поле | Значение |
|---|---|
| Статус | accepted |
| Дата | 2026-11-16 |
| Владелец | Пётр Бондарев (petrobond) |
| Версия релиза | `v3.3.0` |
| Репозиторий | `git@github.com:petrobond/gostrag.git`, ветка `release/v3.0.0` |
| Связанные документы | `plans/09-plan-v3.3-web-ui-auth.md`, `docs/web.md` |

## 1. Контекст

`gostrag` — RAG-система по ГОСТ Р / ПНСТ: FastAPI (`/health`, `POST /api/ask`),
Telegram-бот (публичный, админ-команды только владельцу), Qdrant
`gost_chunks_bge_m3_v3`, PostgreSQL, Redis, корпус `2026.11.13-r2` (4657 чанков).
Деплой — по тегу через GitHub Actions; VPS `ultra` (2 vCPU, 3.3 GiB RAM + 5.7 GiB
swap, свободно ~2 GiB RAM и ~26 GiB диска) используется только как runtime.

Требуется лёгкий веб-интерфейс: вход с авторизацией, чат по ГОСТам, ответы с
цитатами (ГОСТ, пункт, страница, ссылка на PDF с `#page=N`), история диалогов,
роли `user` / `admin`, минимальная админка. Публичный Telegram-бот не должен
деградировать.

Изучены:

- `gostrag`: `app/main.py`, `app/api/ask.py`, `app/rag/service.py`,
  `app/storage/usage.py`, `app/storage/s3.py`, `deploy/docker-compose.yml`,
  `deploy/Dockerfile`, `deploy/.env.example`, `db/init.sql`, тесты и CI;
- `pharma-rag`: `apps/frontend` (89 файлов, 640 KiB исходников, 60+ npm-зависимостей),
  `server/app/api/auth.py`, `sessions.py`, `admin_users.py`,
  `server/app/middleware/auth_middleware.py`, `server/app/models/db_models.py`,
  `server/requirements.txt`, `apps/frontend/Dockerfile.prod`, `nginx.conf`.

Права на код `pharma-rag` подтверждены владельцем (ответ №5, 2026-11-16), но
проект помечен как проприетарный и рассчитан на 8+ vCPU / 32+ GiB RAM. Перенос
целиком нецелесообразен по ресурсам, зависимостям и объёму лишнего UI.

## 2. Варианты

| Критерий | A. Pharma frontend/auth | B. Новый lightweight | C. Комбинация |
|---|---|---|---|
| Скорость получения MVP | 3–5 дней: адаптация 89 файлов React, другой домен, адаптер к API | 7–9 дней: всё с нуля | 5–7 дней: UX-паттерны pharma, код с нуля |
| Сложность сопровождения | Высокая: React 19 + 60+ npm + SQLAlchemy + SMTP + JWT | Низкая: Jinja2 + 2 зависимости + asyncpg | Низкая |
| Зависимости frontend | 60+ npm, Node 20, Vite/Tailwind/Radix/Cytoscape/Recharts | 0 npm, htmx ~16 KiB gzip + CSS | 0 npm |
| Зависимости backend | SQLAlchemy, PyJWT, bcrypt, SMTP, prometheus-client | Jinja2, argon2-cffi (asyncpg уже есть) | Jinja2, argon2-cffi |
| RAM/CPU на VPS | ~200–320 MiB доп. (backend + nginx) | ~50–90 MiB (app + proxy) | ~50–90 MiB |
| Безопасность auth | JWT в `localStorage` (XSS), SMTP-сброс, открытая регистрация | HttpOnly cookie, CSRF, Argon2id, invite-only | HttpOnly cookie, CSRF, Argon2id, invite-only |
| Соответствие текущему API | Нужен адаптер к `/api/ask` + новый auth API | Прямой вызов `AskService` | Прямой вызов `AskService` |
| Объём лишнего UI | ~60–70% (граф, фарма-админка, аналитика) | 0 | 0 |
| Риски и ограничения | ресурсы VPS, поддержка, лицензии npm, чужой код | сроки на вёрстку | сроки/дизайн, зато полный контроль |

## 3. Auth-механизмы

| Критерий | Telegram Login Widget | Email + пароль | Код через бота |
|---|---|---|---|
| Публичный HTTPS-домен | обязателен + BotFather | обязателен | обязателен |
| SMTP | не нужен | не нужен в MVP (invite/reset-ссылки вручную) | не нужен |
| Связь с Telegram | да | нет | да |
| Соответствие ответу владельца («веб без Telegram») | нет | да | нет |
| Реализация | HMAC-SHA256(bot_token), `auth_date`, `id` | Argon2id + серверные сессии + CSRF | коды в Redis + `/web` в боте |
| UX | 1 клик | форма | 2 шага |
| Риски | привязка к TG, настройка домена | брутфорс (закрыт throttle), «забыл пароль» (reset-ссылка админом) | доп. сценарий в боте, коды в чате |

## 4. Решение

**Принят вариант C**: новый лёгкий интерфейс на FastAPI + Jinja2 + htmx,
UX-паттерны `pharma-rag` (карточка логина, sidebar истории, поле вопроса,
карточки ответа и цитат, сценарии login/logout/me/change password/admin-only),
но без переноса кода, стилей и ассетов.

**Auth: email + пароль, только по приглашению**:

- пользователей создаёт администратор (или CLI), публичной регистрации нет;
- `admin` назначается только через CLI, UI создаёт только `user`;
- SMTP в MVP нет: приглашение и сброс пароля — одноразовые ссылки,
  которые админ копирует вручную;
- пароли — Argon2id, сессии — серверные, cookie `HttpOnly`/`Secure`/`SameSite=Lax`,
  CSRF — double-submit, токен сессии в БД только в виде SHA-256.

Не переносится: React/Radix/Cytoscape/Recharts, фарма-админка, граф знаний,
JWT в `localStorage`, SQLAlchemy, SMTP, заявки на регистрацию.

## 5. Модель данных

Отдельные таблицы `web_*`; `qa_log` и `usage_daily` не смешиваются с веб-сессиями.

```text
web_users           id UUID PK, email UNIQUE (lowercase), password_hash, role user|admin,
                    is_active, must_change_password, created_at, last_login
web_sessions        id UUID PK, user_id → web_users, token_hash UNIQUE, expires_at,
                    last_seen_at, created_at, revoked_at, ip INET, user_agent
web_invites         id UUID PK, email, role, purpose invite|reset, token_hash UNIQUE,
                    created_by, expires_at, used_at, created_at
web_conversations   id UUID PK, user_id → web_users, title, created_at, updated_at
web_messages        id UUID PK, conversation_id → web_conversations, role user|assistant,
                    content, citations_json JSONB, refused, latency_ms, model, created_at
web_login_attempts  key TEXT, created_at   -- throttle по IP и sha256(email)
schema_migrations   version TEXT PK, applied_at
```

Миграции лежат в `app/web/migrations.py`, применяются на старте приложения под
`pg_advisory_lock` и идемпотентно; `db/init.sql` не меняется (legacy-схема бота).

## 6. Безопасность

- Argon2id (`time_cost=2`, `memory_cost=19456 KiB`, `parallelism=1`), rehash при
  изменении параметров, хэширование в threadpool.
- Session token — `secrets.token_urlsafe(32)`, в БД только SHA-256; cookie
  `__Host-gostrag_sid` (`Secure`, `HttpOnly`, `SameSite=Lax`, `Path=/`).
- CSRF — double-submit: cookie `__Host-gostrag_csrf` + hidden-поле/`X-CSRF-Token`.
- TTL: абсолютный 7 дней, idle 24 часа; logout/смена пароля/блокировка → revoke.
- Throttle входа: 10 попыток/15 мин на IP, 5/15 мин на email; единый ответ
  «Неверный email или пароль».
- Роли: `admin` только через CLI; UI создаёт только `user`, повышение роли
  через веб невозможно.
- Ответы LLM выводятся как экранированный текст; CSP без inline-скриптов.
- `/api/ask` и `/health` не публикуются наружу; Qdrant/PostgreSQL/Redis остаются
  на `127.0.0.1`.
- В логи не попадают пароли, токены, cookie и тела запросов; invite-ссылки
  исключены из access-логов и `Referrer-Policy: no-referrer`.

## 7. TLS и доступ по IP

Без HTTPS нельзя выставить `Secure` cookie, поэтому доступ по «голому» HTTP
на IP не рассматривается. Варианты:

| Вариант | Цена | Ограничения |
|---|---|---|
| Самоподписанный сертификат на IP | 0 ₽ | предупреждение браузера, HSTS нельзя |
| Let's Encrypt IP-сертификат (профиль `shortlived`) | 0 ₽ | срок 160 часов (~6,7 дня), нужен ACME-клиент с профилями и IP-идентификаторами, профиль может быть в allowlist |
| Бесплатный DNS + LE 90 дней | 0 ₽ | `*.sslip.io` не в PSL (общие лимиты), DuckDNS — в PSL |
| Свой домен + LE | ~200–400 ₽/год | требует покупки и DNS |

Для пилота выбран бесплатный DNS (`<ip>.sslip.io` или DuckDNS), для постоянной
работы — свой домен. Reverse proxy — Caddy в контейнере (авто-TLS, HSTS, CSP,
HTTP→HTTPS), приложение остаётся на `127.0.0.1:8000`.

## 8. Последствия

Положительные: минимальные зависимости и память, нет Node.js в runtime,
прямой вызов существующего `AskService`, серверные cookie-сессии, invite-only,
полный контроль над UI и безопасностью.

Отрицательные: UI написан самостоятельно (нет готовой админ-аналитики и графа),
нужно поддерживать шаблоны и CSS, TLS зависит от домена и открытых портов.

## 9. Ссылки

- `plans/09-plan-v3.3-web-ui-auth.md`
- `docs/web.md`
- `docs/networking.md`
- Let's Encrypt Profiles (Identifier Types, `shortlived`): <https://letsencrypt.org/docs/profiles/>
