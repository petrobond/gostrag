# AGENTS.md — gostrag

## 1. Что это

RAG-система по российским стандартам ИИ (39 PDF: ГОСТ Р и ПНСТ): Telegram-бот,
ответы с цитатами (ГОСТ, пункт, страница), ссылки на PDF в S3 с `#page=N`,
внутренний ГОСТ-аудит (LLM-as-a-judge) и версионированные отчёты.

## 2. Репозиторий и ветки

- repo: `git@github.com:petrobond/gostrag.git`
- рабочая ветка: `release/v3.0.0`
- `main` и `dev` не трогать без команды владельца
- коммиты: Conventional Commits, один этап плана = один коммит

## 3. Правило изменений (обязательно)

Любое отклонение от `plans/08-plan-v3.2-local-first.md` (архитектура, модели,
маршрутизация VPN, объём работ, порядок этапов, хранение данных) согласуется
с владельцем — Петром Бондаревым (petrobond). Без письменного согласования
изменения не вносятся. Согласованное изменение оформляется новой ревизией плана
и записью в «Журнал изменений плана».

Режим работы с 2026-11-13 — **local-first**: разработка, тесты, ingest, embed,
eval, judge и audit выполняются локально; VPS `ultra` — только runtime
(без VS Code Server, сборок, ingest и правок кода). Деплой — по тегу через CI/CD.

## 4. Архитектура

- `bot/` — aiogram 3: `/start`, `/help`, `/gosts`, `/stats`, `/ask`, текст
- `app/` — FastAPI: `POST /api/ask`, `GET /health` (version, commit, collection, kb_ready)
- версия продукта: **3.2.2** (pyproject = APP_VERSION = `/health`)
- CI/CD: GitHub Actions (ruff, pytest, build linux/amd64), GHCR, deploy по тегу `v*`
- образ по умолчанию без `fastembed`/ONNX; `INSTALL_LOCAL_EMBEDDINGS=true` — fallback
- Qdrant — коллекция `gost_chunks_bge_m3_v3` (BGE-M3, 4446 точек, корпус
  2026.11.13-r2); `gost_chunks_bge_m3_v2` (4396) и `gost_chunks_bge_m3` — rollback
- KB/граф — `app/kb`, `data/kb`: 400 терминов, 97 узлов (37 корпусных + 60 внешних),
  116 рёбер (24 внутренних); команды `/kb`, `/term`, `/links`; 1-hop для cross_reference
- Postgres 16 и Redis 7 — в compose; usage пишется в PG (`qa_log`, `usage_daily`), `/stats`
- S3 (Yandex Object Storage) — 39 PDF в `gost/`, presigned URL + `#page`
- LLM: GigaChat-3-Ultra (fallback Max → Pro → Lite → DeepSeek) — только API
- Эмбеддинги: `BAAI/bge-m3` через Cloud.ru Foundation Models API
  (`POST /v1/embeddings`, OpenAI-compatible), 1024d, 8192 контекста, 0.61 ₽/1M
  - `EMBEDDING_PROVIDER=cloudru`, модель внутренняя (данные не логируются)
  - локальная `intfloat/multilingual-e5-large` (ONNX, volume `gostrag_fastembed_cache`)
    — fallback: `EMBEDDING_PROVIDER=local`; модель в образе не нужна
  - резерв API: `Qwen/Qwen3-Embedding-0.6B` (1024d, recall@8 1.000, pass 0.946)
  - таблицы: T01 закрыт слиянием дублей `chunk_id`; TB01 (таблица 6.3) — 8 строк
    по PDF, закрыт в v3.2.0

## 5. Где что запущено

VPS (ultraVDS):

- 45.15.252.185, Ubuntu 26.04, 2 vCPU, 3.3 ГБ RAM + swap 5.7 ГБ, диск 49 ГБ
- пользователь `gostrag` (NOPASSWD sudo), ключ `~/.ssh/petrobond`, алиас `ultra`;
  deploy-ключ `~/.ssh/vps_deploy_key` (ed25519) — для CI/CD
- репозиторий `/opt/gostrag`, ветка `release/v3.0.0`
- запуск: `cd /opt/gostrag && sudo docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d`
- сервисы: `app`, `bot`, `qdrant`, `postgres`, `redis`
- **только runtime**: без VS Code Server, сборок, ingest и правок кода
- секреты: `/opt/gostrag/secrets` (600), `deploy/.env` (600)
- данные: `/opt/gostrag/data/{corpus,index,source}`
- `ProBack_SA` (`proback-rag-bot.service`) — отдельный проект, не трогать

Локально:

- `/Users/Lenovo/Projects/RAG_Timur`, venv `.venv`, Docker Desktop (8.3 ГБ)
- локальный контур: `deploy/docker-compose.local.yml` (qdrant/postgres/redis),
  Qdrant на `127.0.0.1:6335` (6333 занят старым `gostrag-qdrant-1`)
- split tunneling (2026-11-13): Telegram → `utun4`; Cloud.ru, GigaChat, GitHub,
  S3, DeepSeek → `en0` (напрямую); VPS SSH — напрямую
- бэкапы: `backups/2026-11-13/` (Qdrant snapshot, PostgreSQL dump, corpus/index/KB, PDF)

Блокер снят 2026-11-12: AmneziaWG (`awg-quick@awg0`, split tunnel) поднят,
`api.telegram.org` доступен, бот на VPS поллит Telegram.

## 6. Данные и индексы

- корпус: 38 документов, 4657 чанк (3759 clause + 860 table + 38 meta)
- уникальных по `text_hash`: 4495; уникальных `uuid5(chunk_id)`: 4608
- Qdrant: `gost_chunks_bge_m3_v3` (прод/локально, BGE-M3), `gost_chunks_bge_m3_v2`
  и `gost_chunks_bge_m3` — rollback; id = `uuid5(chunk_id)`, payload = чанк целиком
- KB: `data/kb/terms.jsonl` (400), `graph.json` (97 узлов / 116 рёбер), `outline.json` (37 стандартов)
- BM25: `data/index/bm25.pkl` (~6.5 МБ), не зависит от модели эмбеддингов
- переиндексация BGE-M3 на VPS: 150 с (31 чанк/с), стоимость ~0.74 ₽
- артефакты данных: `dist/data-<corpus_version>.tar.gz` + `manifest-*.json`, S3 `data/`
- BM25 обновляется тем же `embed`; путь `/data/index`, а не `/tmp/index`

## 7. Команды

Локально:

```bash
.venv/bin/python -m pytest -q tests          # 89 тестов
.venv/bin/python -m ruff check app bot eval tests
.venv/bin/python scripts/net_matrix.py        # сеть: Telegram, VPS, Cloud.ru, GigaChat
.venv/bin/python scripts/ask.py "вопрос"
.venv/bin/python scripts/eval_retrieval.py --gold eval/gold_set_v2.yaml --top-k 8
.venv/bin/python eval/judge.py --gold eval/gold_set_v2.yaml --out eval/report_v2.json
```

Локальный контур (Docker Desktop):

```bash
make dev-up          # qdrant/postgres/redis
make api             # uvicorn на 127.0.0.1:8000
make test            # pytest
make lint            # ruff
make seed-qdrant     # восстановить snapshot прода
```

Ингест (локально, только при необходимости):

```bash
python -m app.cli ingest --source data/source --out data/corpus
python -m app.cli embed --corpus data/corpus --index data/index --qdrant-url http://qdrant:6333
python -m app.cli data-fetch --version 2026.11.13 --dest /data
```

Переиндексация эмбеддингов через Cloud.ru (VPS, ~3 мин):

```bash
sudo docker compose -f deploy/docker-compose.yml run --rm \
  -e EMBEDDING_PROVIDER=cloudru -e QDRANT_COLLECTION=gost_chunks_bge_m3_v2 \
  app python -m app.cli embed --corpus /data/corpus --index /data/index \
  --qdrant-url http://qdrant:6333
```

Оценка retrieval/judge (VPS, репозиторий монтируется):

```bash
sudo docker compose -f deploy/docker-compose.yml run --rm \
  -e EMBEDDING_PROVIDER=cloudru -e QDRANT_COLLECTION=gost_chunks_bge_m3_v2 \
  -v /opt/gostrag:/repo -w /repo app \
  python scripts/eval_retrieval.py --gold eval/gold_set_v2.yaml --top-k 8 \
  --qdrant-url http://qdrant:6333
```

KB/граф:

```bash
python scripts/build_kb.py          # data/kb
python scripts/build_gold_kb.py     # eval/gold_kb.yaml
```

VPS:

```bash
ssh ultra
cd /opt/gostrag
sudo docker compose -f deploy/docker-compose.yml ps
sudo docker compose -f deploy/docker-compose.yml logs --tail=100 bot
curl -s localhost:8000/health
curl -s localhost:6333/collections/gost_chunks_bge_m3_v2 | head -c 300
```

## 8. Секреты

`secrets/` в `.gitignore`, на VPS `chmod 600`. Не печатать в логи и чат:
`ultraVDS`, `gigachatAPI`, `telegram`, `object_storage`, `deepseekApi`,
`yandexCloud`, `git`, `amnezia.conf` (приватные ключи AWG), `amneziaVPN`.

## 9. Тесты и метрики (v3.2, BGE-M3)

- `pytest`: **89 passed**; ruff clean (app bot eval tests)
- gold v2 (37, BGE-M3): pass **0.973 (36/37)**, recall@8 **1.000 (28/28)**,
  citation 0.963, citation recall **1.000 (54/54)**, faithfulness/relevancy 0.919
- gold v3 (50, 19 стандартов): retrieval **1.000 (41/41)**, pass **1.000 (50/50)**,
  faithfulness/relevancy 0.96/0.96, citation 1.0, citation recall **1.000 (58/58)**;
  M04, X01, TB01, KB10 — pass; v3.2.2 retrieval 1.0, judge 47/50
  (E04/M04/CL02 — strict-judge outliers, C05 исправлен split-part lookup)
- gold-KB (10): **1.000 (10/10)**, citation **28/28** (v3.2.1); KB07 —
  «стандарты корпуса» → внутренняя ветка 71476, п. 2
- audit v3.2: **157 требований / 15 ГОСТов**, N/A 15 (9.55%), coverage **90.45%**,
  compliance applicable **74.65%**; отчёт `docs/reports/3.2.0/1/`
- reranker `bge-reranker-v2-m3`: A/B recall@8 1.000 → 0.740, top1 37 → 23 — **не используется**

## 10. Известные проблемы

- 2026-11-13: VPS — только runtime; `.vscode-server` удалён, build cache очищен
- GigaChat: `verify=True`; Russian Trusted Root/Sub CA в `deploy/certs` (этап 6 закрыт)
- BM25: документированный `--index /tmp/index` не обновлял `bm25.pkl` — исправлено
- GitHub: секреты `VPS_SSH_KEY`/`VPS_HOST`/`VPS_USER` добавлены владельцем;
  environment `production` с required reviewer; deploy — по тегу
- deploy-ключ `~/.ssh/vps_deploy_key` добавлен в VPS `authorized_keys`, проверен
- Telegram с VPS работает через AmneziaWG (`awg-quick@awg0`, split tunnel):
  DNS `100.64.0.1` недоступен, фактически используется `8.8.8.8` через туннель
  (PostUp `resolvectl dns awg0 8.8.8.8; domain awg0 ~telegram.org`)
- Режим `ASK_API_URL` (бот локально → API на VPS) закоммичен (70ed838),
  но **не одобрен и не используется**
- RAM разгружена: app ~212 МБ, bot ~346 МБ, swap ~0.7 ГБ (было 4.65 ГБ);
  `fastembed`/ONNX вынесены в optional extra `local` — базовый образ и процессы
  без них; для локального fallback нужен `pip install -e '.[local]'`
- Cloud.ru — внешняя зависимость на каждый запрос: retry на 429/5xx, таймаут 60 с;
  при 502/503 dense-поиск отключается, ответ идёт по BM25 (`dense_search_unavailable`);
  проверено 2026-11-13 во время аварии Cloud.ru
- M04/TB01/KB10/X01: закрыты; gold v3 **50/50** (v3.2.0)
- KB07: в v3.2.0 external-links перехватывал «стандарты корпуса» и отдавал
  внешние ГОСТы; в v3.2.1 — внутренняя ветка графа (71476, п. 2)
- v3.2.2: `/kb` для 72664 исправлен — разделы 4/5, приложения A/B/C/ДА/ДБ,
  letter-подпункты A.1/C.1, дедупликация outline; ложные разделы 5/6 из таблицы
  приложения ДБ больше не появляются
- deploy: `data/kb` после root-контейнера не давал `git checkout`; добавлен
  chown `data/*` перед checkout (коммит 56bee3e, входит в v3.2.1)
- reranker отклонён по результатам A/B (ухудшает recall/top1)
- клиент Qdrant 1.20.0 против сервера 1.12.4 — warning; запинен `<1.13` (этап 0)

## 11. План

`plans/08-plan-v3.2-local-first.md` (ревизия 1.0):

0. версия/бэкапы, локальный контур, CI, очистка VPS, CD, данные, сеть/CA
7. TB01 — таблица 6.3
8. KB10 — внешние ссылки
9. аудит: ≥120 требований из ≥10 ГОСТов
10. `/audit` + usage в PostgreSQL
11. релиз

Релизы: `v3.1.0` (TB01, KB10, инфраструктура), `v3.2.0` (аудит + `/audit`),
`v3.2.1` (KB07 «стандарты корпуса», deploy chown), `v3.2.2` (структура `/kb`,
outline и corpus `2026.11.13-r2`).

## 12. Чек-лист приёмки этапа 0

- [ ] `awg show` — handshake есть
- [ ] `getent ahostsv4 api.telegram.org` — есть IPv4
- [ ] `curl -4 https://api.telegram.org` — 200/404
- [ ] бот не рестартует, в логах нет `TelegramNetworkError`
- [ ] `/gosts` — 37 стандартов
- [ ] ответ с цитатой и ссылкой `#page`
- [ ] локальный бот остановлен (один poller)

## 13. Инструкция агенту (кратко)

1. Работать локально; VPS не использовать для разработки.
2. Перед изменениями — бэкап (`backups/`), после этапа — тесты, ruff, коммит, пуш.
3. Любое отклонение — стоп и вопрос владельцу.
4. VPS — только деплой готового образа/данных; VS Code Server не возвращать.
5. Секреты не печатать; при 403 на GitHub — остановиться и дать инструкцию владельцу.

