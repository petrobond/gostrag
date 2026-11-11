# gostrag

RAG-система по российским стандартам в области искусственного интеллекта (ГОСТ Р / ПНСТ).
Отвечает на прицельные вопросы по корпусу стандартов, цитирует конкретный пункт и страницу,
проходит внутренний аудит соответствия ГОСТам с помощью LLM-as-a-judge (GigaChat).

## Ключевые решения

- **LLM:** GigaChat 3 Ultra (freemium) с fallback-цепочкой Max → Pro → Lite → DeepSeek (Yandex AI Studio).
- **Эмбеддинги:** GigaEmbeddings-3B-2025-09 (2048 dim, контекст 4096) через GigaChat API.
- **Хранилища:** Qdrant (векторы), PostgreSQL (метаданные, квоты, отчёты), Redis (очередь, кэш).
- **Доступ:** только Telegram-бот, whitelist пользователей.
- **Развёртывание:** локально в Docker Compose, затем перенос на VPS.

## Документы

- `plans/01-plan.md` — подробный план реализации.
- `plans/02-gost-compliance.md` — проверка плана на соответствие ГОСТам и альтернативы.
- `plans/03-gold-set.md` — контрольный набор вопросов для оценки качества.

## Быстрый старт

```bash
cp deploy/.env.example deploy/.env
# заполнить секреты
docker compose -f deploy/docker-compose.yml up -d
```

Секреты хранятся в `secrets/` и в git не попадают.
