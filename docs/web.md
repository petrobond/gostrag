# Веб-интерфейс gostrag

| Поле | Значение |
|---|---|
| Версия | 3.3.0 |
| Решение | `docs/adr/001-web-ui-auth.md`, `plans/09-plan-v3.3-web-ui-auth.md` |
| Доступ | по приглашению, email + пароль, без Telegram |
| Стек | FastAPI + Jinja2 + htmx + PostgreSQL, без Node.js в runtime |

## 1. Назначение и границы

Веб-интерфейс даёт авторизованным пользователям чат по корпусу ГОСТ Р / ПНСТ:
ответы с цитатами (ГОСТ, пункт, страница) и ссылкой на PDF в S3 с `#page=N`,
историю диалогов, смену пароля и минимальную админку.

Что веб-интерфейс **не делает**:

- не загружает документы и не запускает ингест (только локально, см. `AGENTS.md`);
- не содержит графа знаний и фармацевтической аналитики;
- не использует Telegram для входа;
- не публикует `/api/ask` и `/health` в интернет;
- не смешивает `qa_log` / `usage_daily` (бот) с веб-таблицами `web_*`.

Публичный Telegram-бот продолжает работать без изменений.

## 2. Роли и доступ

| Роль | Как назначается | Права |
|---|---|---|
| `user` | приглашение от администратора | чат, свои диалоги, смена пароля |
| `admin` | только CLI (`web-user create --role admin`) | всё выше + статистика, пользователи, документы, аудит |

Публичной регистрации нет. Пользователь не может повысить себе роль: форма
приглашения в админке всегда создаёт `user`.

Администратор не может заблокировать собственную учётную запись.

## 3. Маршруты

| Метод | Путь | Доступ | Назначение |
|---|---|---|---|
| GET | `/` | гость | редирект на `/login` или `/chat` |
| GET | `/login` | гость | форма входа |
| POST | `/login` | гость | вход, установка cookie-сессии |
| POST | `/logout` | user | инвалидация сессии |
| GET | `/me` | user | JSON профиля (401 без сессии) |
| GET | `/invite/{token}` | гость | установка пароля по одноразовой ссылке |
| POST | `/invite/{token}` | гость | принятие приглашения / сброс пароля |
| GET/POST | `/password` | user | смена пароля |
| GET | `/chat`, `/chat/{id}` | user | чат и история (только свои диалоги) |
| POST | `/web/ask` | user | вопрос: HTML-фрагмент (HTMX) или редирект |
| POST | `/web/conversations/new` | user | создать диалог |
| POST | `/web/conversations/{id}/delete` | user | удалить свой диалог |
| GET | `/api/web/conversations` | user | список диалогов |
| POST | `/api/web/conversations` | user | создать диалог |
| GET | `/api/web/conversations/{id}` | user | диалог с сообщениями (чужой → 404) |
| DELETE | `/api/web/conversations/{id}` | user | удалить диалог |
| POST | `/api/web/ask` | user | JSON-ответ: поля `/api/ask` + `conversation_id`, `message_id`, `citations[].pdf_url` |
| GET | `/api/web/admin/stats` | admin | статистика (user → 403) |
| GET | `/admin` | admin | статистика |
| GET | `/admin/users` | admin | пользователи и приглашения |
| POST | `/admin/users/invite` | admin | создать приглашение (роль `user`) |
| POST | `/admin/users/{id}/block`, `/unblock` | admin | блокировка |
| POST | `/admin/users/{id}/reset` | admin | одноразовая ссылка сброса пароля |
| GET | `/admin/documents` | admin | документы корпуса (read-only) |
| GET | `/admin/audit` | admin | отчёты аудита (read-only) |
| GET | `/admin/audit/view?root=…&path=…` | admin | просмотр отчёта, только внутри whitelist-каталога |
| GET | `/health` | локально | состояние, в т.ч. `web_ready` |

## 4. Безопасность

- Пароли — Argon2id (`time_cost=2`, `memory_cost=19456 KiB`, `parallelism=1`),
  проверка и хэширование выполняются в threadpool.
- Сессия — случайный `token_urlsafe(32)`; в БД только SHA-256. Cookie
  `__Host-gostrag_sid`: `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`.
- CSRF — double-submit: cookie `__Host-gostrag_csrf` + hidden-поле или
  заголовок `X-CSRF-Token`; при наличии `Sec-Fetch-Site` проверяется origin.
- TTL сессии: 7 дней абсолютный, 24 часа idle (`WEB_SESSION_TTL_DAYS`,
  `WEB_SESSION_IDLE_HOURS`). Logout, смена пароля и блокировка отзывают сессии.
- Throttle входа: 10 попыток / 15 мин на IP и 5 / 15 мин на email,
  единый ответ «Неверный email или пароль».
- Ответы LLM выводятся как экранированный текст (`white-space: pre-wrap`),
  сырой HTML и Markdown не исполняются. CSP запрещает inline-скрипты.
- В логи не пишутся пароли, токены, cookie и тела запросов; invite-ссылки
  исключены из access-логов Caddy, `Referrer-Policy: no-referrer`.
- Qdrant, PostgreSQL и Redis остаются на `127.0.0.1`; наружу публикуется
  только reverse proxy.

## 5. Данные и миграции

Таблицы создаются миграциями из `app/web/migrations.py` при старте приложения
(`WEB_AUTOMIGRATE=true`, `pg_advisory_lock`, таблица `schema_migrations`).
`db/init.sql` не меняется — это legacy-схема бота.

```text
web_users           id, email UNIQUE (lowercase), password_hash, role user|admin,
                    is_active, must_change_password, created_at, last_login
web_sessions        id, user_id, token_hash UNIQUE, expires_at, last_seen_at,
                    created_at, revoked_at, ip, user_agent
web_invites         id, email, role, purpose invite|reset, token_hash UNIQUE,
                    created_by, expires_at, used_at, created_at
web_conversations   id, user_id, title, created_at, updated_at
web_messages        id, conversation_id, role user|assistant, content,
                    citations_json JSONB, refused, latency_ms, model, created_at
web_login_attempts  key, created_at
```

Приложение работает и без PostgreSQL: `/health` → `web_ready=false`,
веб-страницы отдают 503, `/api/ask` и бот продолжают работать.

Ручной запуск миграций:

```bash
sudo docker compose -f deploy/docker-compose.yml run --rm app python -m app.cli db migrate
```

Бэкап: `pg_dump` в `scripts/remote_deploy.sh` включает веб-таблицы автоматически.

## 6. Переменные окружения

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `WEB_ENABLED` | `true` | включить веб-маршруты |
| `WEB_DOMAIN` | пусто | публичный домен для Caddy и ссылок приглашений (без схемы) |
| `WEB_COOKIE_SECURE` | `true` | `Secure` + префикс `__Host-` (локально `false`) |
| `WEB_SESSION_TTL_DAYS` | `7` | абсолютный срок сессии |
| `WEB_SESSION_IDLE_HOURS` | `24` | idle-таймаут |
| `WEB_AUTOMIGRATE` | `true` | применять миграции на старте |
| `WEB_MAX_CONCURRENT_ASKS` | `4` | семафор одновременных вопросов |
| `WEB_LOGIN_IP_LIMIT` | `10` | попыток входа на IP за окно |
| `WEB_LOGIN_EMAIL_LIMIT` | `5` | попыток входа на email за окно |
| `WEB_LOGIN_WINDOW_MIN` | `15` | окно throttle, минуты |
| `WEB_INVITE_TTL_DAYS` | `7` | срок жизни приглашения/сброса |
| `WEB_PASSWORD_MIN_LEN` | `12` | минимальная длина пароля |

## 7. TLS и reverse proxy

`deploy/Caddyfile` публикует `WEB_DOMAIN` по HTTPS (автоматический Let's Encrypt),
включает HSTS, CSP и security-заголовки, кэширует `/static/*`, исключает
`/invite/*` из access-логов и отдаёт 404 на `/api/ask` и `/health`.

Сервис `proxy` в `deploy/docker-compose.yml` включён в профиль `proxy`, поэтому
без `WEB_DOMAIN` он не запускается, а приложение продолжает работать на
`127.0.0.1:8000`. Деплой сам включает профиль, если `WEB_DOMAIN` задан.

Доступ по «голому» IP не используется: без HTTPS нельзя выставить `Secure` cookie.
Варианты домена и ограничения описаны в ADR (`docs/adr/001-web-ui-auth.md`).

## 8. Эксплуатация

### 8.1. Первый администратор

На VPS после деплоя:

```bash
cd /opt/gostrag
sudo docker compose -f deploy/docker-compose.yml --env-file deploy/.env \
  run --rm app python -m app.cli web-user create \
  --email bondarev-petr@yandex.ru --role admin
```

Команда печатает одноразовую ссылку `https://<WEB_DOMAIN>/invite/<token>`.
Владелец открывает её и задаёт пароль. Пароль в команды и `.env` не попадает.

### 8.2. Пользователи и приглашения

- создать приглашение: `/admin/users` → «Создать приглашение»;
- ссылка одноразовая, живёт `WEB_INVITE_TTL_DAYS`, передаётся вручную (SMTP нет);
- сброс пароля: `/admin/users` → «Сброс пароля» (тоже одноразовая ссылка);
- блокировка: `/admin/users` → «Блок», сессии пользователя отзываются сразу;
- роль `admin` через веб не назначается.

CLI-эквиваленты:

```bash
python -m app.cli web-user list
python -m app.cli web-user create --email user@example.ru          # invite-ссылка
python -m app.cli web-user create --email user@example.ru --role admin --password-stdin
python -m app.cli web-user passwd --email user@example.ru          # пароль из stdin/tty
python -m app.cli web-user invite --email user@example.ru          # reset-ссылка
```

### 8.3. Проверка

```bash
curl -s localhost:8000/health | python -m json.tool    # web_ready: true
bash scripts/smoke_web.sh http://127.0.0.1:8000
curl -s -o /dev/null -w '%{http_code}\n' https://$WEB_DOMAIN/login  # 200
curl -s -o /dev/null -w '%{http_code}\n' https://$WEB_DOMAIN/api/ask  # 404
```

### 8.4. Логи

```bash
sudo docker compose -f deploy/docker-compose.yml logs --tail=100 app
sudo docker compose -f deploy/docker-compose.yml --profile proxy logs --tail=100 proxy
```

В логах нет паролей, токенов и cookie; пишутся только события (`web login ok`,
`web invite issued` и т.п.).

## 9. Локальная разработка и тесты

```bash
make dev-up                     # qdrant/postgres/redis
make api                        # uvicorn + WEB_COOKIE_SECURE=false
```

`make api` выставляет `WEB_COOKIE_SECURE=false`, иначе браузер не отправит
`Secure`-cookie по HTTP. На проде всегда `true`.

Тесты:

```bash
.venv/bin/python -m pytest -q tests
.venv/bin/python -m ruff check app bot eval tests

# интеграционные тесты веб-таблиц (нужен PostgreSQL)
TEST_POSTGRES_DSN='postgresql://gostrag:gostrag@127.0.0.1:5432/gostrag' \
  .venv/bin/python -m pytest -q tests/test_web_store_pg.py
```

Без `TEST_POSTGRES_DSN` интеграционные тесты пропускаются.

Добавить локального администратора:

```bash
.venv/bin/python -m app.cli web-user create \
  --email admin@example.ru --role admin --password-stdin
```

## 10. Ограничения

- SMTP нет: приглашения и сброс пароля передаются вручную одноразовой ссылкой.
- Публичной регистрации нет; пользователей создаёт администратор.
- Графа знаний, загрузки документов и ингеста в вебе нет (local-first).
- Роль `admin` назначается только через CLI.
- `qa_log` / `usage_daily` не используются веб-интерфейсом; статистика веба
  считается по `web_messages`.
- Telegram Login и OTP через бота не используются (решение владельца).

## 11. Диагностика

| Симптом | Причина | Действие |
|---|---|---|
| `/health` → `web_ready: false` | PostgreSQL недоступен или миграции упали | `docker compose logs app`, проверить `POSTGRES_DSN`, выполнить `db migrate` |
| Логин возвращает 401 | неверный пароль, пользователь заблокирован или throttle | проверить `/admin/users`, подождать окно 15 минут |
| Логин «проходит», но `/chat` снова ведёт на `/login` | `WEB_COOKIE_SECURE=true` по HTTP или домен не совпадает | открыть сайт по HTTPS, проверить `WEB_DOMAIN` |
| `https://…/login` не открывается | DNS/порты 80/443/сертификат | `docker compose --profile proxy logs proxy`, проверить DNS и firewall |
| 403 на формах | истёк/отсутствует CSRF-cookie | обновить страницу, проверить cookie `__Host-gostrag_csrf` |
| Ответ 502 | LLM/Qdrant недоступны | повторить позже, проверить `docker compose logs app`, `/health` |
| 429 | лимит вопросов или параллельных запросов | подождать, проверить `WEB_MAX_CONCURRENT_ASKS` и дневные лимиты |
