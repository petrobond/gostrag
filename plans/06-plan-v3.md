# План v3.0.0: переезд на VPS, база знаний и PDF-источники

| Поле | Значение |
|---|---|
| Версия плана | 3.0.0 |
| Ревизия плана | 1.1 (добавлен AmneziaWG и правило согласования) |
| Дата | 2026-11-12 |
| База | v2.1: pass rate 0.973 (36/37), recall@8 1.000, citation recall 0.944 |
| Ветка | `release/v3.0.0` |
| Репозиторий | `git@github.com:petrobond/gostrag.git` |
| VPS | 45.15.252.185 (ultraVDS), доступ — `secrets/ultraVDS` (не в git) |

## Принятые решения

| № | Вопрос | Решение |
|---|---|---|
| 1 | Объём KB | только определения из разделов «Термины и определения» (~150) |
| 2 | Хранилище usage | PostgreSQL |
| 3 | PDF-источники | только presigned S3 + inline-кнопки (без своего viewer) |
| 4 | Reranker | не внедряем |
| 5 | Ветка | `release/v3.0.0` |
| 6 | VPN для Telegram | AmneziaWG на VPS по `secrets/amnezia.conf` (нативный AWG-конфиг) |
| 7 | Где работает бот | **на VPS**, после поднятия VPN; разделение бота и ядра не применяется |

> **Правило изменений.** Любое отклонение от этого плана (архитектура, объём работ,
> порядок этапов, состав моделей, маршрутизация VPN, хранение данных) согласуется
> с владельцем — Петром Бондаревым (petrobond). Без явного письменного согласования
> изменения не вносятся. Согласованное изменение оформляется новой версией плана
> с записью в разделе «Журнал изменений плана».

## Отклонённые решения

| Решение | Статус |
|---|---|
| Разделение: бот локально → API на VPS (`ASK_API_URL`) | **не применяется**. Бот работает на VPS; режим остаётся в коде как неактивная опция и не используется без согласования |
| Собственный HTML-viewer источников | не делаем: только presigned S3 + `#page` + inline-кнопки |
| Reranker `bge-reranker-v2-m3` | не внедряем (решение владельца) |


---

# Этап 0. Переезд на VPS (блокирующий)

Цель: система работает на VPS 45.15.252.185, локальный контур заглушён, секреты и данные
перенесены, бэкапы настроены. Только после этого начинаются фичи v3.

## 0.1. Предполётная подготовка (локально)

```bash
cd /Users/Lenovo/Projects/RAG_Timur
git status --porcelain          # должно быть пусто
git push origin release/v2.0.0
git push -u origin release/v3.0.0

# бэкап секретов (в git не попадают: secrets/ в .gitignore)
tar czf /tmp/gostrag-secrets.tgz secrets/
```

Проверить ресурсы VPS после входа: `nproc`, `free -h`, `df -h`, `cat /etc/os-release`.
Требования: ≥2 vCPU, ≥4 ГБ RAM (иначе swap 2 ГБ), ≥40 ГБ диска.

Артефакты для переноса:

| Артефакт | Размер | Способ |
|---|---|---|
| `data/corpus` | 11 МБ | rsync |
| `data/index` | 6.4 МБ | rsync |
| `data/source` (39 PDF) | 84 МБ | rsync (опционально, PDF уже в S3) |
| Qdrant `gost_chunks` | ~30–50 МБ | snapshot через API |
| `secrets/` | < 1 КБ | scp/rsync, chmod 600 |

## 0.2. Доступ и базовая защита

Пароль root/user — в `secrets/ultraVDS` (в плане и в git не хранится).
`sshpass` на macOS нет, поэтому первичный вход — через Python + paramiko (или вручную).

```bash
# локально, одноразово
.venv/bin/pip install paramiko
```

Скрипт бутстрапа (локально, пароль читается из `secrets/ultraVDS`, скрипт не коммитить).

Команды на VPS (от root):

```bash
adduser --disabled-password --gecos "" gostrag
usermod -aG sudo gostrag
mkdir -p /home/gostrag/.ssh && chmod 700 /home/gostrag/.ssh
# публичный ключ ~/.ssh/petrobond.pub добавить в authorized_keys
chown -R gostrag:gostrag /home/gostrag/.ssh

apt update && apt install -y docker.io docker-compose-plugin git rsync ufw fail2ban
usermod -aG docker gostrag

ufw allow 22/tcp && ufw --force enable
systemctl enable --now fail2ban

# если RAM < 4 ГБ
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

После проверки входа по ключу:

```bash
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
systemctl reload ssh
```

## 0.2a. AmneziaWG VPN на VPS (обязательно для Telegram)

Проблема: с VPS `api.telegram.org` недоступен (DNS отдаёт только IPv6, IPv4/DC фильтруются),
бот в контейнере перезапускается. Решение: поднять AmneziaWG-туннель на VPS.

Исходные данные:

| Файл | Назначение |
|---|---|
| `secrets/amnezia.conf` | готовый нативный AmneziaWG-конфиг (obfuscation: `Jc/Jmin/Jmax/S1–S4/H1–H4/I1`, `[Peer] Endpoint 201.8.67.239:8581`) |
| `secrets/amneziaVPN` | Amnezia Premium (`service_protocol=awg`, `api_key`) — резервный вариант, требует GUI/API, только по согласованию |

Оба файла — секреты: в git не попадают, на VPS права `600`, в плане и логах не печатать.

### Установка (userspace, без kernel-модуля)

```bash
sudo apt install -y golang-go make gcc git
# amneziawg-go — userspace-реализация
sudo git clone https://github.com/amnezia-vpn/amneziawg-go /opt/amneziawg-go
cd /opt/amneziawg-go && sudo make && sudo make install
# amneziawg-tools — awg, awg-quick
sudo git clone https://github.com/amnezia-vpn/amneziawg-tools /opt/amneziawg-tools
cd /opt/amneziawg-tools/src && sudo make && sudo make install
awg --version && awg-quick --help | head -3
```

Версии фиксировать в `docs/operations.md` (тег/commit), обновление — только по согласованию.

### Конфигурация

```bash
sudo install -d -m 700 /etc/amnezia/amneziawg
sudo install -m 600 /opt/gostrag/secrets/amnezia.conf /etc/amnezia/amneziawg/awg0.conf
```

Маршрутизация — **split tunnel только для Telegram** (безопасно для SSH):

- в установленной копии `awg0.conf` заменить `AllowedIPs` на список Telegram CIDR:
  `91.108.4.0/22, 91.108.8.0/22, 91.108.12.0/22, 91.108.16.0/22, 91.108.20.0/22,
  91.105.192.0/23, 149.154.160.0/20, 185.76.151.0/24, 2001:67c:4e8::/48`;
- полный туннель (`0.0.0.0/0, ::/0`) — **только с письменного согласования владельца**:
  риск потерять SSH при смене default route.

```bash
sudo systemctl enable --now awg-quick@awg0
sudo systemctl status awg-quick@awg0 --no-pager
sudo awg show
```

DNS: в конфиге `DNS = 100.64.0.1, 8.8.4.4`. Проверить, что VPS и контейнеры получают
A-записи (а не только AAAA):

```bash
getent ahostsv4 api.telegram.org
docker run --rm curlimages/curl -s -o /dev/null -w '%{http_code}\n' https://api.telegram.org
```

Если контейнеры не видят VPN-маршрут — добавить MASQUERADE для `awg0` и/или policy routing
для docker-сети `172.18.0.0/16`; изменение фиксируется в плане (правило согласования).

### Приёмка VPN

| Проверка | Команда | Ожидание |
|---|---|---|
| туннель | `awg show` | peer, handshake < 2 мин, transfer > 0 |
| связность | `ping -c 3 100.64.0.1` | 0% loss |
| DNS | `getent ahostsv4 api.telegram.org` | есть IPv4 |
| Telegram | `curl -4 -s -o /dev/null -w '%{http_code}' https://api.telegram.org` | `200` (или `404` на `/`) |
| из контейнера | `docker run --rm curlimages/curl ...` | `200/404` |
| бот | `docker compose logs bot` | нет `TelegramNetworkError`, нет рестартов |
| бот в Telegram | `/gosts`, вопрос | ответ со ссылкой на PDF |

### Откат VPN

```bash
sudo systemctl disable --now awg-quick@awg0
sudo awg-quick down awg0 || true
```

### Риски VPN

| Риск | Митигация |
|---|---|
| Потеря SSH при full tunnel | split tunnel по умолчанию; full tunnel — только по согласованию; держать вторую SSH-сессию |
| Утечка приватных ключей | конфиг только в `secrets/`, `chmod 600`, не печатать в логах, gitleaks |
| DNS только AAAA | VPN DNS + `getent ahostsv4`, при необходимости `dns:` в compose |
| MTU/фрагментация | `MTU = 1280` при проблемах с TLS |
| Несовместимость версий awg | фиксировать версии `amneziawg-go`/`amneziawg-tools`, тест после обновления |

Резервный вариант (если нативный конфиг не поднимется): AmneziaVPN GUI под Xvfb +
импорт `secrets/amneziaVPN` — **только по согласованию**, т.к. GUI-автоматизация хрупкая.

## 0.3. Авторизация GitHub (пользователь petrobond)

Ключ `~/.ssh/petrobond` уже используется для `github.com` (см. `~/.ssh/config`).

Вариант А — быстрый (перенос ключа):

```bash
scp ~/.ssh/petrobond gostrag@45.15.252.185:~/.ssh/petrobond
ssh gostrag@45.15.252.185 '
  chmod 600 ~/.ssh/petrobond
  printf "Host github.com\n  HostName github.com\n  User git\n  IdentityFile ~/.ssh/petrobond\n  IdentitiesOnly yes\n" >> ~/.ssh/config
  chmod 600 ~/.ssh/config
  ssh -T git@github.com
'
# ожидаемо: "Hi petrobond! You've successfully authenticated"
```

Вариант Б — безопаснее: сгенерировать ключ на VPS, добавить его в GitHub через API
(токен — в `secrets/git`), локальный приватный ключ на VPS не копировать.

## 0.4. Клонирование и секреты

```bash
ssh gostrag@45.15.252.185 '
  sudo mkdir -p /opt/gostrag && sudo chown gostrag:gostrag /opt/gostrag
  git clone git@github.com:petrobond/gostrag.git /opt/gostrag
  cd /opt/gostrag && git checkout release/v3.0.0
'

rsync -av secrets/ gostrag@45.15.252.185:/opt/gostrag/secrets/
ssh gostrag@45.15.252.185 'chmod 600 /opt/gostrag/secrets/*'
```

`deploy/.env` собирается из `deploy/.env.example` и секретов:

| Переменная | Источник |
|---|---|
| `GIGACHAT_CREDENTIALS` | `secrets/gigachatAPI` |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_USER_IDS`, `TELEGRAM_ADMIN_IDS` | `secrets/telegram` |
| `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` | `secrets/object_storage` + бакет `proback-rag-docs-b1gksr2m9mcfhrbof7nf` |
| `DEEPSEEK_API_KEY` | `secrets/deepseekApi` |
| `YC_FOLDER_ID`, `YC_API_KEY` | `secrets/yandexCloud` |
| `POSTGRES_DSN`, `REDIS_URL`, `QDRANT_URL` | внутренние адреса compose |
| `EMBEDDING_CACHE_DIR` | `/opt/gostrag/.cache/fastembed` |
| `DATA_SOURCE_DIR` / `DATA_CORPUS_DIR` | `/opt/gostrag/data/source` / `/opt/gostrag/data/corpus` |
| `REPORTS_DIR` | `/opt/gostrag/reports` |

Права: `chmod 600 deploy/.env`; `.env` в git не попадает.

## 0.5. Перенос данных

```bash
rsync -av data/corpus data/index gostrag@45.15.252.185:/opt/gostrag/data/
rsync -av data/source/ gostrag@45.15.252.185:/opt/gostrag/data/source/
```

Qdrant-снапшот (предпочтительно вместо переиндексации):

```bash
# локально
curl -s -X POST "http://localhost:6333/collections/gost_chunks/snapshots"
# взять имя файла из ответа и скачать
curl -s -o /tmp/gost_chunks.snapshot \
  "http://localhost:6333/collections/gost_chunks/snapshots/<snapshot-name>"
scp /tmp/gost_chunks.snapshot gostrag@45.15.252.185:/tmp/
```

Восстановление на VPS (после запуска Qdrant):

```bash
docker cp /tmp/gost_chunks.snapshot $(docker ps -qf name=qdrant):/qdrant/snapshots/
curl -s -X PUT "http://localhost:6333/collections/gost_chunks/snapshots/recover" \
  -H 'Content-Type: application/json' \
  -d '{"location":"file:///qdrant/snapshots/gost_chunks.snapshot"}'
```

Альтернатива: переиндексация на VPS (`app.cli ingest` + `app.cli embed`, ~40 мин на 2 vCPU).
Модель эмбеддингов предзагрузить:
`python -c "from fastembed import TextEmbedding; TextEmbedding('intfloat/multilingual-e5-large')"`.


## 0.6. Запуск и приёмка

```bash
cd /opt/gostrag
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d qdrant postgres redis
# восстановить снапшот (см. 0.5), затем:
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d app bot
docker compose -f deploy/docker-compose.yml logs -f bot
```

Приёмка этапа 0:

| Проверка | Команда | Ожидание |
|---|---|---|
| health | `curl -s localhost:8000/health` | `{"status":"ok"}` |
| коллекция | `curl -s localhost:6333/collections/gost_chunks` | `points_count ≈ 4452`, `status green` |
| бот | `/gosts` | 37 стандартов |
| вопрос | «Что говорится в п. 3.6.4 ГОСТ Р 71476—2024?» | ответ + цитата |
| PDF | ссылка из цитаты | HEAD 200, `#page=N` |
| VPN | `awg show`, `curl -4 api.telegram.org` | handshake есть, HTTP 200/404 |
| конфликт | `grep -i conflict` в логах | пусто (один poller) |

## 0.7. Заглушить локальную систему

```bash
# локальный бот остановить ДО старта VPS-бота (Telegram: один poller)
ps ax -o pid,command | grep 'MacOS/Python -m bot.main' | grep RAG_Timur
kill <pid>
```

Локальный Qdrant и данные не удалять — остаются как standby для отката.
После приёмки VPS локальный бот не запускать.

## 0.8. Бэкапы и мониторинг

```bash
# cron на VPS (пример)
0 3 * * * cd /opt/gostrag && docker compose exec -T postgres pg_dump -U gostrag gostrag | gzip > /opt/backups/pg-$(date +\%F).sql.gz
15 3 * * * curl -s -X POST http://localhost:6333/collections/gost_chunks/snapshots
*/5 * * * * curl -fsS http://localhost:8000/health || curl -s "https://api.telegram.org/bot$TOKEN/sendMessage" -d chat_id=$ADMIN -d text="gostrag down"
```

Бэкапы складывать в `/opt/backups` и раз в сутки — в S3 `backups/` (тот же бакет).
Ротация: 7 ежедневных + 4 недельных.

## 0.9. Откат

1. `docker compose stop bot` на VPS.
2. Запустить локального бота на `release/v2.0.0` (локальные Qdrant/индекс сохранены).
3. Проверить `/gosts` и один вопрос; разобрать причину.

## 0.10. Оценка этапа

0.5–1 день (с учётом переноса данных и приёмки).

## 0.11. Статус этапа 0 на 2026-11-12

| Пункт | Статус | Факт |
|---|---|---|
| VPS, пользователь, Docker, UFW, fail2ban, swap | ✅ | Ubuntu 26.04, 2 vCPU, 3.3 ГБ + swap 2 ГБ, `gostrag` + NOPASSWD sudo |
| GitHub-доступ (`petrobond`) | ✅ | `ssh -T git@github.com` → `Hi petrobond!` |
| Репозиторий и ветка | ✅ | `/opt/gostrag`, `release/v3.0.0` |
| Секреты и `deploy/.env` | ✅ | 44 переменные, права `600` |
| Qdrant | ✅ | v1.12.4, снапшот восстановлен: 4452 точки, `green` |
| Postgres / Redis | ✅ | healthy |
| app | ✅ | `/health` → `index_ready=true`, version 3.0.0 |
| S3-ссылки | ✅ | `enabled=true, keys=39`, цитаты содержат `file`, `#page=N` |
| **VPN (0.2a)** | ⛔ | **не поднят** |
| **Telegram** | ⛔ | `api.telegram.org` недоступен (DNS только IPv6, IPv4/DC фильтруются) |
| **Бот на VPS** | ⛔ | контейнер стартует, но не может поллить Telegram |
| Локальный бот | ⏸ | остановлен; локальный Qdrant оставлен как standby |

Блокер этапа 0 — отсутствие VPN. До поднятия AmneziaWG бот на VPS неработоспособен.


---

# Этап 1. PDF-источники и кнопки (EPIC B)

Проблема: PDF загружены в S3 (39 объектов, presigned URL отдаёт 200), но
`S3Store.enabled = False`, потому что бот запущен без S3-переменных и
`secrets/object_storage` не читается. Цитаты выводятся текстом без ссылок.

| № | Задача | Файл | Критерий |
|---|---|---|---|
| B1 | `read_secret()` для `secrets/object_storage`, env-override, bucket по умолчанию, лог `s3 enabled/keys` | `app/config.py`, `app/storage/s3.py` | в логе `s3 enabled=true, keys=39` |
| B2 | Кэш presigned URL (TTL 7 дней, обновление за 1 час до истечения) | `app/storage/s3.py` | нет повторной подписи на каждый ответ |
| B3 | Inline-кнопки «📄 п. X, с. N» (до 5) по образцу `build_keyboard` из ProBack_SA | `bot/main.py` | кнопки открывают PDF на странице |
| B4 | Unit-тест сборки URL + smoke HEAD 200 и `#page=N` | `tests/` | 10/10 ссылок 200 |
| B5 | `/pdf <ГОСТ> <пункт>` и `GET /api/sources/{chunk_id}` → 302 на presigned | `bot/`, `app/api/` | — |
| B6 | Метрика «доля содержательных ответов с рабочей ссылкой» | `eval/` | ≥ 0.95 |

Оценка: 0.5 дня. Закрывает NFR-06 и замечание «нельзя открыть PDF на странице».

---

# Этап 2. База знаний (EPIC A)

Решение: KB строится только по определениям из разделов «Термины и определения» (~150),
плюс граф нормативных ссылок.

| № | Задача | Артефакт | Критерий |
|---|---|---|---|
| A1 | Извлечение определений: секции «Термины и определения», паттерн «термин: определение», дедуп по (термин, ГОСТ) | `data/kb/terms.jsonl` | ≥150 терминов, precision ≥0.9 на выборке 30 |
| A2 | Граф «стандарт → стандарт» (91 ребро) + разделы как узлы | `data/kb/graph.json` | 91/91 рёбер, 38 узлов-стандартов |
| A3 | KB-сервис: `find_term`, `outline(gost)`, `neighbors(gost)`, `path(a,b)` | `app/kb/` | unit-тесты |
| A4 | Бот: `/kb` (стандарт → разделы → пункт + PDF), `/term`, `/links` | `bot/main.py` | навигация по 3 уровням |
| A5 | KB-aware retrieval: синонимы терминов в запросе + 1 hop по нормативной ссылке | `app/rag/` | cross_reference ≥ 0.9, definition без регресса |
| A6 | Gold-KB: 10 вопросов (термин, граф, ссылки) | `eval/gold_kb.yaml` | pass ≥ 0.85 |

Оценка: 2–3 дня.


---

# Этап 3. Аудит в боте и usage в PostgreSQL

Проблема: `/audit` — заглушка, хотя скрипт аудита работает; usage не логируется,
`/stats` показывает корпус, а не использование; `db/init.sql` не используется кодом.

| № | Задача | Файл | Критерий |
|---|---|---|---|
| C1 | `/audit` и `/audit_status` в боте: переиспользовать `scripts/audit.py`, вернуть отчёт и файл | `bot/main.py`, `app/audit/` | отчёт создаётся один раз на (user, version) |
| C2 | Запись `qa_log`, `usage_daily`, токенов; миграции при старте | `app/storage/db.py`, `app/rag/service.py` | строки появляются после вопроса |
| C3 | `/stats`: вопросы, отказы, p50/p95, токены за 7 дней | `bot/main.py` | цифры совпадают с БД |
| C4 | Дневной cap токенов + алерт при 80% | `app/guard/` | тест на лимит |

Оценка: 1.5 дня. Закрывает FR-06, FR-09, FR-10, NFR-09.

---

# Этап 4. Redis, лимиты и UX

| № | Задача | Критерий |
|---|---|---|
| D1 | Кэш ответов `cache:answer:{sha256(question+corpus_version)}`, TTL 24 ч | повторный вопрос < 200 мс |
| D2 | Redis-лок `lock:gigachat` (1 поток, TTL 90 с) | нет параллельных вызовов |
| D3 | Антифлуд 1 запрос / 5 с на пользователя | тест |
| D4 | Reply-клавиатура: «Задать вопрос», «Список ГОСТов», «База знаний», «Помощь» | кнопки в боте |
| D5 | `/reindex` (админ): ingest + embed с подтверждением | команда работает |
| D6 | Query expansion аббревиатур (ИИ, ML, RAG, LLM) | unit-тест |

Оценка: 1.5–2 дня. Закрывает §8.4, §9.2–9.3, FR-12, §7.1.

---

# Этап 5. Безопасность и тесты

| № | Задача | Критерий |
|---|---|---|
| E1 | gitleaks в pre-commit + прогон по истории | чисто |
| E2 | PII-редакция логов (email, телефон) | unit-тест |
| E3 | Circuit breaker по дневному бюджету | тест на 80% |
| E4 | Integration-тесты: Qdrant, S3, Postgres | 3 сценария |
| E5 | E2E с mock Telegram | вопрос → ответ с кнопкой |
| E6 | Нагрузка: 10 параллельных вопросов | p95 ≤ 20 с, без 429-шторма |
| E7 | Решение по overlap 10–15% в чанкинге (внедрить или зафиксировать отклонение) | ADR |

Оценка: 2 дня. Закрывает §10, §13, NFR-10/11.

---

# Этап 6. Оценка, документация, релиз

| № | Задача | Критерий |
|---|---|---|
| F1 | Gold-KB (10 вопросов) + прогон judge | KB pass ≥ 0.85 |
| F2 | Полный прогон gold v2 (37 вопросов) на VPS | pass ≥ 0.95, без регресса |
| F3 | Обновить `docs/`: architecture (KB), provenance (S3), operations (VPS), test_plan | матрица заполнена |
| F4 | Отчёт аудита на VPS, версия 3.0.0 | отчёт + manifest |
| F5 | Тег `v3.0.0`, merge в `dev`/`main` по команде | — |

Оценка: 1 день.

---

# Сводка этапов

| Этап | Содержание | Оценка | Блокирует |
|---|---|---|---|
| 0 | Переезд на VPS + AmneziaWG | 1–1.5 дня | все остальные |
| 1 | PDF-ссылки и кнопки | 0.5 дня | — |
| 2 | База знаний | 2–3 дня | этап 6 (gold-KB) |
| 3 | Аудит в боте + usage (PG) | 1.5 дня | этап 6 |
| 4 | Redis, лимиты, UX | 1.5–2 дня | — |
| 5 | Безопасность и тесты | 2 дня | релиз |
| 6 | Оценка, docs, релиз 3.0.0 | 1 день | — |
| **Итого** | | **≈ 9–11 дней** | |

---

# Целевые метрики v3

| Метрика | Сейчас (v2.1) | Цель v3 |
|---|---|---|
| Pass rate gold v2 | 0.973 (36/37) | ≥ 0.95 без регресса |
| Comparison (M04) | fail | ≥ 0.9 (5/5) |
| KB: терминов | 12 (вручную) | ≥ 150 |
| KB: граф ссылок | 0 | 91 ребро |
| KB pass (10 вопросов) | — | ≥ 0.85 |
| Доля ответов с рабочей PDF-ссылкой | 0% | ≥ 95% |
| Citation recall | 0.944 | ≥ 0.95 |
| p95 latency | 3.8 с | ≤ 20 с |
| Cost | не измерен | ≤ 2000 ₽/мес, usage-отчёт из PG |
| e2e/load тесты | 0 | 3 сценария |
| Uptime на VPS | — | 99% в рабочие часы |

---

# Риски

| Риск | Вероятность | Влияние | Митигация |
|---|---|---|---|
| Два poller (локальный и VPS) → Telegram 409 | Высокая | Высокое | остановить локальный бота до старта VPS (0.7) |
| Потеря доступа к VPS при смене sshd | Средняя | Высокое | проверить ключ в отдельной сессии до `reload ssh` |
| S3-ключи в git | Низкая | Высокое | `secrets/` в `.gitignore`, gitleaks |
| Не хватит RAM для e5-large | Средняя | Среднее | swap 2 ГБ, лимиты compose, кэш модели на диске |
| Расхождение Qdrant-снапшота и версии сервера | Средняя | Среднее | одинаковый образ `qdrant/qdrant:v1.20.0` |
| Telegram не открывает `#page` в части клиентов | Средняя | Низкое | кнопка + `/pdf`, ссылка в тексте |
| KB-слой дублирует retrieval | Средняя | Низкое | KB только навигация и синонимы |
| Postgres/Redis усложняют эксплуатацию | Низкая | Среднее | healthchecks, бэкапы, лимиты памяти |
| Telegram недоступен с VPS | **Высокая (факт)** | **Высокое** | AmneziaWG split tunnel (0.2a), проверка `curl -4 api.telegram.org` |
| Потеря SSH при full tunnel | Средняя | Высокое | split tunnel по умолчанию; full tunnel только по согласованию |
| Утечка AWG-конфига (приватные ключи) | Низкая | Высокое | `secrets/`, `chmod 600`, не печатать, gitleaks |

---

# Definition of Done (v3.0.0)

- [ ] VPS 45.15.252.185: бот и API работают, локальный заглушён.
- [ ] AmneziaWG поднят (split tunnel), `api.telegram.org` с VPS отвечает 200/404.
- [ ] Бот на VPS поллит Telegram без `TelegramNetworkError` и лишних рестартов.
- [ ] Секреты на VPS с правами 600, в git отсутствуют, gitleaks чист.
- [ ] Бэкапы Postgres и Qdrant по расписанию, healthcheck с алертом.
- [ ] PDF открывается на нужной странице из текста и из кнопки; ≥95% ответов со ссылкой.
- [ ] `/kb`, `/term`, `/links` работают; ≥150 терминов, 91 ребро.
- [ ] `/audit` и `/audit_status` в боте; отчёт версионирован и идемпотентен.
- [ ] Usage пишется в Postgres; `/stats` показывает вопросы, отказы, p50/p95, токены.
- [ ] Redis-кэш и лок GigaChat работают.
- [ ] Integration/e2e/load тесты проходят.
- [ ] Gold v2 ≥ 0.95, gold-KB ≥ 0.85.
- [ ] Тег `v3.0.0`, документация обновлена.

---

# Открытые вопросы к реализации

1. VPN: подтвердить split tunnel (Telegram CIDR) как основной вариант; full tunnel — только по отдельному согласованию.
2. VPN: устраивает ли userspace `amneziawg-go` (без kernel-модуля) или нужен DKMS-модуль.
3. Пользователь на VPS: `gostrag` (рекомендуется) или `user` из `secrets/ultraVDS`?
4. GitHub-ключ: переносить `~/.ssh/petrobond` на VPS (быстро) или генерировать новый (безопаснее)?
5. Репозиторий на VPS: `/opt/gostrag` (по умолчанию в плане) — согласовать.
6. Домен/TLS: нужен ли Caddy и домен для API или достаточно localhost + Telegram?

---

# Журнал изменений плана

| Ревизия | Дата | Изменение | Основание |
|---|---|---|---|
| 1.0 | 2026-11-12 | Первая версия: VPS-переезд, KB, PDF-источники, долги планов 01/05 | Владелец |
| 1.1 | 2026-11-12 | Добавлен этап 0.2a (AmneziaWG: установка, split tunnel, DNS, приёмка, откат, риски); добавлено правило согласования отклонений; зафиксированы отклонённые решения и статус этапа 0 | Указание владельца |

