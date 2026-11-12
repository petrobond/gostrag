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

Любое отклонение от `plans/06-plan-v3.md` (архитектура, модели, маршрутизация VPN,
объём работ, порядок этапов, хранение данных) согласуется с владельцем — Петром
Бондаревым (petrobond). Без письменного согласования изменения не вносятся.
Согласованное изменение оформляется новой ревизией плана и записью в «Журнал
изменений плана». Не принимать самостоятельных решений о разделении сервисов
(например, «бот локально, ядро на VPS»).

## 4. Архитектура

- `bot/` — aiogram 3: `/start`, `/help`, `/gosts`, `/stats`, `/ask`, текст
- `app/` — FastAPI: `POST /api/ask`, `GET /health`
- Qdrant — коллекция `gost_chunks_bge_m3` (прод, 4452 точки), `gost_chunks` — старая коллекция e5 (rollback), v1.12.4
- Postgres 16 и Redis 7 — в compose; usage в PG пока не пишется (этап 3 плана)
- S3 (Yandex Object Storage) — 39 PDF в `gost/`, presigned URL + `#page`
- LLM: GigaChat-3-Ultra (fallback Max → Pro → Lite → DeepSeek) — только API
- Эмбеддинги: `BAAI/bge-m3` через Cloud.ru Foundation Models API
  (`POST /v1/embeddings`, OpenAI-compatible), 1024d, 8192 контекста, 0.61 ₽/1M
  - `EMBEDDING_PROVIDER=cloudru`, модель внутренняя (данные не логируются)
  - локальная `intfloat/multilingual-e5-large` (ONNX, volume `gostrag_fastembed_cache`)
    — fallback: `EMBEDDING_PROVIDER=local`; модель в образе не нужна
  - резерв API: `Qwen/Qwen3-Embedding-0.6B` (1024d, recall@8 1.000, pass 0.946)
  - таблица/чанкинг: T01 (полный список `Acc-I-*`) — известный дефект, этап 2

## 5. Где что запущено

VPS (ultraVDS):

- 45.15.252.185, Ubuntu 26.04, 2 vCPU, 3.3 ГБ RAM + swap 2 ГБ
- пользователь `gostrag` (NOPASSWD sudo), ключ `~/.ssh/petrobond`, алиас `ultra`
- репозиторий `/opt/gostrag`, ветка `release/v3.0.0`
- запуск: `cd /opt/gostrag && sudo docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d`
- сервисы: `app`, `bot`, `qdrant`, `postgres`, `redis`
- секреты: `/opt/gostrag/secrets` (600), `deploy/.env` (600)
- данные: `/opt/gostrag/data/{corpus,index,source}`

Локально:

- `/Users/Lenovo/Projects/RAG_Timur`, venv `.venv`

Блокер снят 2026-11-12: AmneziaWG (`awg-quick@awg0`, split tunnel) поднят,
`api.telegram.org` доступен, бот на VPS поллит Telegram.

## 6. Данные и индексы

- корпус: 38 документов, 4791 чанк (3825 clause + 928 table + 38 meta)
- уникальных по `text_hash`: 4643; уникальных `uuid5(chunk_id)`: 4452
- Qdrant: `gost_chunks_bge_m3` (прод) и `gost_chunks` (e5, rollback) — по 4452 точки,
  id = `uuid5(chunk_id)`, payload = чанк целиком
- BM25: `data/index/bm25.pkl` (~6.5 МБ), не зависит от модели эмбеддингов
- переиндексация BGE-M3 на VPS: 150 с (31 чанк/с), стоимость ~0.74 ₽

## 7. Команды

Локально:

```bash
.venv/bin/python -m pytest -q tests          # 50 тестов
.venv/bin/python -m ruff check app bot eval tests
.venv/bin/python scripts/ask.py "вопрос"
.venv/bin/python scripts/eval_retrieval.py --gold eval/gold_set_v2.yaml --top-k 8
.venv/bin/python eval/judge.py --gold eval/gold_set_v2.yaml --out eval/report_v2.json
```

Ингест (только при необходимости, ~40–60 мин на VPS):

```bash
python -m app.cli ingest --source data/source --out data/corpus
python -m app.cli embed --corpus data/corpus --index data/index --qdrant-url http://qdrant:6333
```

Переиндексация эмбеддингов через Cloud.ru (VPS, ~3 мин):

```bash
sudo docker compose -f deploy/docker-compose.yml run --rm \
  -e EMBEDDING_PROVIDER=cloudru -e QDRANT_COLLECTION=gost_chunks_bge_m3 \
  app python -m app.cli embed --corpus /data/corpus --index /tmp/index \
  --qdrant-url http://qdrant:6333
```

Оценка retrieval/judge (VPS, репозиторий монтируется):

```bash
sudo docker compose -f deploy/docker-compose.yml run --rm \
  -e EMBEDDING_PROVIDER=cloudru -e QDRANT_COLLECTION=gost_chunks_bge_m3 \
  -v /opt/gostrag:/repo -w /repo app \
  python scripts/eval_retrieval.py --gold eval/gold_set_v2.yaml --top-k 8 \
  --qdrant-url http://qdrant:6333
```

VPS:

```bash
ssh ultra
cd /opt/gostrag
sudo docker compose -f deploy/docker-compose.yml ps
sudo docker compose -f deploy/docker-compose.yml logs --tail=100 bot
curl -s localhost:8000/health
curl -s localhost:6333/collections/gost_chunks | head -c 300
```

## 8. Секреты

`secrets/` в `.gitignore`, на VPS `chmod 600`. Не печатать в логи и чат:
`ultraVDS`, `gigachatAPI`, `telegram`, `object_storage`, `deepseekApi`,
`yandexCloud`, `git`, `amnezia.conf` (приватные ключи AWG), `amneziaVPN`.

## 9. Тесты и метрики (v3.1, BGE-M3)

- `pytest`: 56 passed
- gold v2 (37, BGE-M3): pass **0.973 (36/37)**, recall@8 **1.000 (28/28)**,
  citation 0.963, citation recall **1.000 (54/54)**, faithfulness/relevancy 0.919
- gold v3 (50, 19 стандартов): retrieval/judge — после восстановления Cloud.ru (сейчас 500);
  текущий гейт — gold v2 **0.973 (36/37)**
- контроль e5: pass 0.973 (36/37), 0.919/0.919/0.906
- известный провал: M04 (comparison: 15 характеристик 71484.2 vs измеримые показатели 72663) —
  атрибуция между ГОСТами; E02/T01 закрыты
- reranker `bge-reranker-v2-m3`: A/B recall@8 1.000 → 0.740, top1 37 → 23 — **не используется**

## 10. Известные проблемы

- Telegram с VPS работает через AmneziaWG (`awg-quick@awg0`, split tunnel):
  DNS `100.64.0.1` недоступен, фактически используется `8.8.8.8` через туннель
  (PostUp `resolvectl dns awg0 8.8.8.8; domain awg0 ~telegram.org`)
- Режим `ASK_API_URL` (бот локально → API на VPS) закоммичен (70ed838),
  но **не одобрен и не используется**
- RAM разгружена: app ~212 МБ, bot ~346 МБ, swap ~0.7 ГБ (было 4.65 ГБ);
  `qdrant-client` всё ещё импортирует `fastembed`/ONNX (~100 МБ на процесс) —
  вынести в optional extra при уборке
- Cloud.ru — внешняя зависимость на каждый запрос: retry на 429/5xx, таймаут 60 с;
  при 502/503 dense-поиск отключается, ответ идёт по BM25 (`dense_search_unavailable`);
  проверено 2026-11-13 во время аварии Cloud.ru
- M04: comparison-ответ путает атрибуцию 15 характеристик (71484.2) и измеримых
  показателей (72663); E02/T01 исправлены title-aware anchor и слиянием дублей `#8.2`
- reranker отклонён по результатам A/B (ухудшает recall/top1)
- клиент Qdrant 1.20.0 против сервера 1.12.4 — warning, запинить клиент <1.13

## 11. План

`plans/06-plan-v3.md` (ревизия 1.1):

0. переезд на VPS + AmneziaWG (0.2a) — блокирующий
1. PDF-ссылки и inline-кнопки
2. база знаний (только определения из «Термины и определения», ~150; граф 91 ребро)
3. `/audit` в боте + usage в PostgreSQL
4. Redis-кэш/лок, антифлуд, клавиатура, `/reindex`, query expansion
5. безопасность и тесты (gitleaks, PII, circuit breaker, e2e/load)
6. gold-KB, оценка, docs, релиз v3.0.0

## 12. Чек-лист приёмки этапа 0

- [ ] `awg show` — handshake есть
- [ ] `getent ahostsv4 api.telegram.org` — есть IPv4
- [ ] `curl -4 https://api.telegram.org` — 200/404
- [ ] бот не рестартует, в логах нет `TelegramNetworkError`
- [ ] `/gosts` — 37 стандартов
- [ ] ответ с цитатой и ссылкой `#page`
- [ ] локальный бот остановлен (один poller)

## 13. Инструкция агенту (кратко)

1. Проверить состояние VPS, ничего не менять до понимания картины.
2. Выполнить этап 0.2a (AmneziaWG, split tunnel) строго по плану.
3. Любое отклонение — стоп и вопрос владельцу.
4. После VPN перезапустить бот, проверить чек-лист этапа 0.
5. Далее этапы 1–6: тесты, коммит, пуш, короткий отчёт после каждого этапа.

