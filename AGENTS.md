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
- Qdrant — коллекция `gost_chunks`, 4452 точки, v1.12.4
- Postgres 16 и Redis 7 — в compose; usage в PG пока не пишется (этап 3 плана)
- S3 (Yandex Object Storage) — 39 PDF в `gost/`, presigned URL + `#page`
- LLM: GigaChat-3-Ultra (fallback Max → Pro → Lite → DeepSeek) — только API
- Эмбеддинги: `intfloat/multilingual-e5-large`, ONNX Runtime, локально, 1024d
  - модель НЕ в образе: Docker volume `gostrag_fastembed_cache` (~2.1 ГБ)
  - fastembed не добавляет префиксы e5 (`query:`/`passage:`) — кандидат на
    улучшение, требует согласования и переиндексации

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
- уникальных по `text_hash`: 4643
- Qdrant: 4452 точки, id = `uuid5(chunk_id)`, payload = чанк целиком
- BM25: `data/index/bm25.pkl` (~6.5 МБ)
- на VPS Qdrant восстановлен из снапшота, переиндексация не нужна

## 7. Команды

Локально:

```bash
.venv/bin/python -m pytest -q tests          # 45 тестов
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

## 9. Тесты и метрики (v2.1)

- `pytest`: 45 passed
- gold v2: pass rate **0.973 (36/37)**, recall@8 **1.000**, citation recall **0.944**
- judge: faithfulness 0.919, relevancy 0.919, citation 0.906, refusal 0.973
- известный провал: M04 (71484.2 vs 72663) — сравнение характеристик и показателей

## 10. Известные проблемы

- Telegram с VPS работает через AmneziaWG (`awg-quick@awg0`, split tunnel):
  DNS `100.64.0.1` недоступен, фактически используется `8.8.8.8` через туннель
  (PostUp `resolvectl dns awg0 8.8.8.8; domain awg0 ~telegram.org`)
- Режим `ASK_API_URL` (бот локально → API на VPS) закоммичен (70ed838),
  но **не одобрен и не используется**
- `app` и `bot` — два процесса, каждый может держать копию e5 (~0.8–1.5 ГБ);
  на 3.3 ГБ RAM это риск OOM — решение только по согласованию
- префиксы e5 не добавляются — потенциальный прирост качества после переиндексации

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

