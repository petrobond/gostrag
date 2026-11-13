# План v3.2: local-first разработка, CI/CD и закрытие качества

| Поле | Значение |
|---|---|
| Версия плана | 3.2.0 |
| Дата | 2026-11-13 |
| Ветка | `release/v3.0.0` |
| Репозиторий | `git@github.com:petrobond/gostrag.git` |
| Прод | VPS `ultra` (45.15.252.185), `/opt/gostrag` |
| Основание | аудит 2026-11-13, решения владельца 1–10 |

## Решения владельца (2026-11-13)

| № | Решение |
|---|---|
| 1 | Вариант A: сначала `v3.1.0` (фиксы + инфраструктура), затем `v3.2.0` (аудит ≥120 + `/audit`) |
| 2 | `/audit` — только admin + whitelist |
| 3 | Deploy key `~/.ssh/vps_deploy_key` (ed25519, без passphrase); публичная часть добавлена в VPS `authorized_keys` |
| 4 | На VPS чистить всё, кроме `ProBack_SA` (отдельный проект, должен работать) |
| 5 | Раздельное туннелирование на Mac настроено владельцем; проверено — работает |
| 6 | Docker Desktop запущен (8.3 ГБ RAM, aarch64) |
| 7 | `TELEGRAM_TEST_BOT_TOKEN` добавлен в `secrets/telegram` |
| 8 | Установка Russian Trusted CA и отказ от `verify=False` подтверждены |
| 9 | S3 для `data/` и `backups/` подтверждён |
| 10 | Дубликат PDF можно удалить |

## 0. Зафиксированное состояние

- Локально: ветка `release/v3.0.0`, 65 тестов, Docker 29.9.3 (aarch64, 8.3 ГБ).
- Сеть Mac: Telegram через `utun4` (302), Cloud.ru 200, GigaChat 401, Sber 405,
  GitHub 200, S3 200, DeepSeek 401 — split tunneling работает.
- VPS: `/health` 3.0.0, Qdrant `gost_chunks_bge_m3` 4452 точки, 3.3 ГБ RAM,
  диск 19/49 ГБ, `.vscode-server` 803 МБ, build cache 4.9 ГБ, `ProBack_SA` 213 МБ.
- Бэкапы 2026-11-13: `backups/2026-11-13/` (corpus/index/KB, 39 PDF, Qdrant snapshot
  56 МБ с checksum, PostgreSQL dump, deploy/.env локально и VPS).
- TB01: таблица 6.3 — 8 строк (2 на с. 8 + 6 на с. 9); `t8-1/t8-2` — таблицы 6.1/6.2,
  ошибочно подписаны 6.3; gold содержит только 2 строки — дефект gold подтверждён.
- GigaChat: клиент использует `verify=False`; в certifi нет Russian Trusted Root CA.
- BM25: `app.cli embed` пишет `bm25.pkl` в `--index`; документированный `/tmp/index`
  не обновляет BM25 на VPS.
- Версия: `pyproject.toml` 0.1.0, `deploy/.env` на VPS 3.0.0, отчёт аудита 3.1.0,
  git-теги отсутствуют.
- GitHub: репозиторий публичный, default branch `main`, workflows отсутствуют;
  `gh`-аккаунт `PBondarevOctaneRent` имеет только `pull` на `petrobond/gostrag`.

## 1. Принципы

1. Разработка, ingest, embed, eval, judge, audit — только локально.
2. VPS — только runtime: без VS Code Server, сборок, ingest и правок кода.
3. Один poller: локальный бот с прод-токеном не запускается.
4. Иммутабельные образы: сборка в CI, деплой по тегу, откат на предыдущий тег.
5. Данные — версионированные артефакты (S3 + manifest + sha256).
6. Один этап = один коммит; после этапа — тесты, ruff, пуш, короткий отчёт.

## 2. Этапы

### Этап 0. Версия и единый источник (0.5 дня)

- `pyproject.toml` → `3.1.0`; `deploy/.env.example` → `APP_VERSION=3.1.0`.
- `pyproject.toml`: `qdrant-client>=1.12,<1.13` (сервер 1.12.4).
- `/health`: `version`, `commit`, `collection`, `kb_ready`.
- `GIT_COMMIT` пробрасывается в image и `/health`.
- Проверка: тесты 65+, ruff clean.
- Коммит: `chore(release): align version, pin qdrant client and expose health`.

### Этап 1. Локальный контур (1–2 дня)

- `deploy/docker-compose.local.yml`: qdrant v1.12.4, postgres 16, redis 7,
  порты только `127.0.0.1` (Qdrant — `6335`, чтобы не конфликтовать с локальным
  `gostrag-qdrant-1` на 6333), volumes в `.local/`.
- `Makefile`: `dev-up`, `dev-down`, `dev-status`, `api`, `test`, `lint`,
  `eval-retrieval`, `judge`, `audit`, `seed-qdrant`.
- `scripts/qdrant_snapshot.py`: `download`, `restore`, `list`.
- Локальный Qdrant: восстановить snapshot прода (4452 точки) или `app.cli embed`.
- `.env.local` (gitignored) + экспорт переменных в `Makefile`.
- Проверка: локальный `/health`, `/api/ask` с цитатой, тесты/ruff.
- Коммит: `feat(dev): local docker stack and dev commands`.

### Этап 2. CI (1 день)

- `.github/workflows/ci.yml`: push/PR в `release/**`; ruff, pytest, build linux/amd64.
- Маркер `integration` для сетевых тестов; в CI — только unit.
- `gitleaks` и, опционально, `pip-audit`.
- Коммит: `ci: add lint, tests and image build workflow`.

### Этап 3. Разгрузка VPS (0.5 дня)

- Удалить `~/.vscode-server` (803 МБ), процесс `code agent host`.
- `docker builder prune -af` (4.9 ГБ), `docker image prune -f`, удалить
  неиспользуемый `curlimages/curl`.
- `journalctl --vacuum-size=200M`, `SystemMaxUse=200M`, `apt-get clean`.
- `ProBack_SA` не трогать; проверить, что сервис `proback-rag-bot` жив.
- Цель: диск ≤30%, available RAM ≥1.5 ГБ, build cache 0.
- Коммит: `docs(ops): VPS cleanup report and disk budget`.

### Этап 4. CD и образы (2 дня)

- Multi-stage `deploy/Dockerfile`; runtime без `build-essential` и `curl`;
  слой зависимостей кэшируется; образ ≤600 МБ.
- `deploy/docker-compose.yml`: `image: ${APP_IMAGE}`, без `build`,
  log rotation 10m×3, healthcheck app, `APP_VERSION`/`GIT_COMMIT`.
- `deploy/docker-compose.build.yml` — локальная сборка.
- `.github/workflows/release.yml`: tag `v*` → GHCR `:<version>` и `:sha-<short>`.
- `.github/workflows/deploy.yml`: tag `v*` + environment `production`
  (required reviewer) → SSH на VPS → backup → pull → up → health/smoke → rollback.
- Секреты GitHub: `VPS_SSH_KEY`, `VPS_HOST`, `VPS_USER`; при private GHCR — `GHCR_PAT`.
- Fallback: `scripts/deploy.sh` с локального Mac.
- Коммиты: `build: multi-stage image and pull-based compose`,
  `ci: add release and deploy workflows`.

### Этап 5. Данные и Qdrant как артефакты (1–2 дня)

- `scripts/package_data.py`: `dist/data-<corpus_version>.tar.zst` + `manifest.json`
  (sha256, counts, embedding model, collection, git commit).
- `scripts/publish_data.py`: S3 `data/<corpus_version>/`, проверка sha256.
- `app/cli.py data-fetch`: скачать, проверить, атомарно заменить `data/{corpus,index,kb}`.
- Исправить BM25: one-shot `embed` пишет в `/data/index` через `docker-compose.data.yml`.
- Qdrant: локальный snapshot + restore (основной) или reindex на VPS (резерв, 150 с).
- Бэкапы: Qdrant snapshot + `pg_dump` перед деплоем, retention 30 дней.
- Коммит: `feat(data): versioned data artifacts, S3 fetch and BM25 refresh`.

### Этап 6. Сеть, TLS и документация (1 день)

- `scripts/net_matrix.py`: VPS SSH, Telegram, Cloud.ru, GigaChat, GitHub, S3, DeepSeek,
  локальные Qdrant/PG/Redis; exit code 1 при критическом провале.
- `docs/networking.md`: include-only Telegram, direct для VPS/Cloud.ru/GigaChat/GitHub/S3,
  DNS, типовые ошибки, откат профиля.
- TLS: `deploy/certs/` (Russian Trusted Root/Sub CA), `SSL_CERT_FILE`, `verify=True`,
  удалить `verify=False` из `app/llm/gigachat.py`.
- Тест: `GigaChatClient.models()` с проверкой TLS.
- Коммиты: `docs(net): split tunneling and connectivity matrix`,
  `fix(llm): verify GigaChat TLS with Russian Trusted CA`.

### Этап 7. TB01 (2–3 дня)

- Парсер: bbox таблицы и caption; «Продолжение/Окончание таблицы N»; не смешивать таблицы;
  смена таблицы по заголовку колонок.
- Чанкер: `table_number`, `table_id`, `table_caption`, `row_start`, `row_end`,
  `row_count`, `header`, `part`, `parts_total`; повтор header при разбиении;
  детерминированный `chunk_id`.
- Exact lookup: `extract_table_ref`, `ChunkStore.table_chunks(gost, table_number)`,
  фильтр Qdrant `gost_number` + `table_number`, все части по `(page, row_start)`.
- Prompt: только строки таблицы из контекста; перечислить все части; не добавлять
  строки других таблиц; сказать о неполноте.
- Gold: все 8 строк таблицы 6.3 (проверено по PDF), citation ПНСТ 844—2023, таблица 6.3.
- Тесты: `test_table_chunking.py`, `test_table_lookup.py`.
- Переиндексация локально в `gost_chunks_bge_m3_v2`; eval retrieval + judge.
- Приёмка: TB01 pass, gold v3 ≥0.99, retrieval 1.000, нет строк 6.1/6.2.
- Коммит: `fix(ingest): isolate table chunks and add exact table lookup`.

### Этап 8. KB10 (0.5–1 день)

- `KnowledgeBase.external_neighbors(gost)`: только `internal=False`, dedupe, сортировка.
- Intent-паттерны: «какие внешние стандарты упоминает», «нормативные ссылки»,
  «на какие стандарты ссылается», «внешние ссылки <ГОСТ>».
- `_append_kb_links`: детерминированный ответ, `refused=False`, citation п. 2 с. 5,
  без внутренних ссылок.
- `/links` использует тот же метод.
- Тесты: ровно 4 внешних, intent, citation, gold-KB KB10.
- Приёмка: gold-KB 1.0 (10/10).
- Коммит: `fix(kb): deterministic external links for reference questions`.

### Этап 9. Покрытие аудита (2–3 дня)

- `eval/requirements.yaml` ≥120 требований из ≥10 ГОСТов; поля `applicability`,
  `applicability_reason`, `evidence_hint`, `page`, `chunk_id`.
- `scripts/extract_requirements.py` — кандидаты из корпуса с page/chunk_id; ручная проверка.
- N/A ≤15%, coverage ≥90%.
- `scripts/audit_evidence.py` → `docs/audit_evidence.md/.json` (pytest, ruff, health,
  `/gosts`, KB, gold, version/commit, контейнеры/память).
- `scripts/audit.py`: evidence в `ARTIFACT_FILES`, лимит пересмотреть.
- Метрики: `coverage`, `compliance_all`, `compliance_applicable` в md/manifest/PG.
- Judge: enum статусов, evidence с ссылкой, N/A с reason, unknown → partial,
  batch 3, temperature 0, `strict=False`.
- Коммит: `feat(audit): expand requirements, evidence and metrics`.

### Этап 10. `/audit` в боте + usage (2 дня)

- `/audit` — admin + whitelist, 1 отчёт на пользователя/версию, `/audit_status`.
- Отчёты в `REPORTS_DIR/<version>/<user_id>/`, идемпотентность.
- `qa_log`/`usage_daily` в PostgreSQL; `/stats` — вопросы, отказы, p50/p95, токены.
- Тесты: fake LLM, идемпотентность, доступ, PG-репозиторий.
- Коммит: `feat(bot): audit command and PostgreSQL usage`.

### Этап 11. Релиз (0.5 дня)

- Вариант A: `v3.1.0` (TB01, KB10, инфраструктура), затем `v3.2.0` (аудит + `/audit`).
- Тесты ≥80, ruff clean, gold v2 ≥0.973, gold v3 ≥0.99, gold-KB 1.0, retrieval 1.000.
- Деплой через CD, smoke `/health`, `/gosts`, вопрос с цитатой, `/links`.
- Бэкап, откат проверен, тег, GitHub Release, отчёт.

## 3. CI/CD

| Событие | Действие |
|---|---|
| push в `release/**` | ruff + pytest + build linux/amd64 (без push) |
| tag `v*` | build/push GHCR + deploy после approval environment `production` |

Секреты: `VPS_SSH_KEY` (содержимое `~/.ssh/vps_deploy_key`), `VPS_HOST`,
`VPS_USER`; `GHCR_PAT` — только если пакет private.

Важно: `workflow_dispatch` требует workflow на `main`; поэтому деплой — по tag push
с required reviewer. `main` не трогаем.

## 4. Сеть

| Ресурс | Маршрут | Статус |
|---|---|---|
| `api.telegram.org` | `utun4` | 302 |
| `foundation-models.api.cloud.ru` | `en0` | 200 |
| `api.giga.chat` | `en0` | 401 (TLS CA нужен для verify=True) |
| `ngw.devices.sberbank.ru` | `en0` | 405 |
| `github.com` / `ghcr.io` | `en0` | 200 / 401 |
| `storage.yandexcloud.net` | `en0` | 200 |
| `api.deepseek.com` | `en0` | 401 |
| `45.15.252.185:22` | direct | OK |

## 5. Риски и откат

| Риск | Митигация |
|---|---|
| GitHub Actions не достучится до VPS | fallback `scripts/deploy.sh`; deploy key проверен |
| GHCR private/недоступен | S3 tarball + `docker load`; или PAT |
| Сборка ломает runtime | multi-stage + smoke + откат `previous` |
| Данные/BM25 рассинхрон | manifest + sha256 + бэкап + проверка `chunks_total` |
| Qdrant snapshot несовместим | reindex на VPS через Cloud.ru |
| VPN-профиль рвёт SSH | отдельная сессия, direct route, откат профиля |
| GigaChat CA не установится | временно `verify=False` + запись в риски |
| TB01 gold снова неполный | сверка с PDF, 8 строк, judge допускает доп. корректные строки |
| Аудит раздут N/A | каждый N/A с reason, coverage ≥90% |

## 6. Definition of Done

- [ ] Версия едина: pyproject = APP_VERSION = `/health` = manifest.
- [ ] Локальный контур: Qdrant 4452, `/api/ask`, 65+ тестов, ruff clean.
- [ ] CI зелёный; образ linux/amd64; GHCR доступен.
- [ ] CD: tag + approval, деплой, health, rollback.
- [ ] Данные: package/publish/fetch, BM25 обновляется, snapshot/reindex проверен.
- [ ] VPS: `.vscode-server` удалён, build cache 0, диск ≤30%, RAM ≥1.5 ГБ,
      5 сервисов healthy, `ProBack_SA` работает, один poller.
- [ ] Сеть: матрица зелёная на одном профиле.
- [ ] GigaChat TLS с проверкой, без `verify=False`.
- [ ] TB01: 8 строк, нет строк 6.1/6.2, citation корректна, gold pass.
- [ ] KB10: 4 внешних стандарта, citation п. 2, gold-KB 1.0.
- [ ] Аудит: ≥120/≥10 ГОСТов, N/A ≤15%, coverage ≥90%, runtime evidence.
- [ ] `/audit` — admin + whitelist, 1 отчёт на пользователя/версию; usage в PG.
- [ ] Тег `v3.1.0`/`v3.2.0` согласован, релиз задеплоен, отчёт.

## 7. Журнал изменений плана

| Ревизия | Дата | Изменение |
|---|---|---|
| 1.0 | 2026-11-13 | Первая версия: local-first, CI/CD, очистка VPS, сеть/CA, TB01, KB10, аудит, `/audit`, релиз |


