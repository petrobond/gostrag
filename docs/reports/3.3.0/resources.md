# Ресурсы v3.3.0 (веб-интерфейс)

| Поле | Значение |
|---|---|
| Дата локальных замеров | 2026-11-16 |
| Стенд | macOS, Python 3.12 venv, PostgreSQL 16 (Docker Desktop) |
| VPS-замеры | заполнить после деплоя `v3.3.0` (команды ниже) |

## 1. Локальные замеры

Метод: два запуска `uvicorn app.main:app` с одинаковыми `INDEX_DIR`, `DATA_CORPUS_DIR`,
`QDRANT_URL` и `POSTGRES_DSN`; RSS снимался через `ps -o rss=` после `/health`.
Первый запуск — `WEB_ENABLED=true`, второй — `WEB_ENABLED=false`.

| Режим | RSS, KiB | RSS, MiB |
|---|---|---|
| с веб-слоем | 290 576 | ~283.8 |
| без веб-слоя | 278 352 | ~271.8 |
| **дельта веб-слоя** | **12 224** | **~11.9** |

Веб-слой: Jinja2, шаблоны, Argon2, пул asyncpg (1–4 соединения), миграции,
static. Модель эмбеддингов повторно не загружается.

## 2. Статика

| Файл | Байт | gzip |
|---|---|---|
| `htmx.min.js` (2.0.4, vendored) | 50 917 | 16 399 |
| `app.css` | 9 978 | 2 620 |
| `app.js` | 740 | 349 |
| **Итого** | **61 635** | **~19 368 (~18.9 KiB)** |

Лимиты задания: ≤5 MiB статики и ≤250 KiB gzip JS — выполнены с большим запасом.

## 3. Оценка на VPS

| Компонент | Доп. RAM | Доп. диск |
|---|---|---|
| `app` (веб-слой) | +12–25 MiB | ~2 МБ (зависимости в образе) |
| `proxy` (Caddy 2) | +25–40 MiB | ~60 МБ образ, ~100 КБ сертификаты |
| PostgreSQL (6 таблиц) | +5–10 MiB | ~1–2 МБ |
| **Итого** | **~50–90 MiB** (бюджет 150) | статика ~61 KiB |

## 4. Замеры на VPS (после деплоя)

Базовая линия на 2026-11-16: занято ~1.3 GiB RAM, свободно ~2.0 GiB;
`app` ~174 MiB, `bot` ~307 MiB, Qdrant ~40 MiB, PostgreSQL ~21 MiB,
Redis ~2 MiB; swap ~0.7 GiB; свободно ~26 GiB диска.

```bash
free -m
swapon --show
sudo docker stats --no-stream --format \
  'table {{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}'
sudo du -sh /opt/gostrag/app/web 2>/dev/null || true
sudo docker system df
```

Чек-лист:

- [ ] `app` RSS вырос не более чем на 25 MiB;
- [ ] `proxy` RSS ≤ 45 MiB;
- [ ] суммарный прирост ≤ 150 MiB;
- [ ] swap не вырос относительно базовой линии;
- [ ] диск: прирост ≤ 100 МБ (образ Caddy + сертификаты);
- [ ] `curl -s localhost:8000/health` → `web_ready: true`.
