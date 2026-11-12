from __future__ import annotations

import asyncio
import html
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.guard.rate_limit import SlidingWindowLimiter  # noqa: E402
from app.kb.kb import KnowledgeBase  # noqa: E402
from app.rag.service import AskService  # noqa: E402
from app.storage.s3 import S3Store  # noqa: E402

settings = get_settings()
dp = Dispatcher()
hour_limiter = SlidingWindowLimiter(settings.hourly_questions_per_user, 3600)
day_limiter = SlidingWindowLimiter(settings.daily_questions_per_user, 86400)
service: AskService | None = None
s3 = S3Store(settings)
try:
    kb: KnowledgeBase | None = KnowledgeBase()
except (FileNotFoundError, ValueError):
    kb = None


class RemoteAnswerService:
    """Bot in remote mode: calls the RAG API on the VPS instead of loading the index."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    async def ask(self, question: str, top_k: int | None = None) -> SimpleNamespace:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self.base_url}/api/ask",
                json={"question": question, "top_k": top_k or 6},
            )
            response.raise_for_status()
            data = response.json()
        answer = SimpleNamespace(
            answer=data.get("answer", ""),
            citations=[SimpleNamespace(**item) for item in data.get("citations", [])],
            refused=bool(data.get("refused")),
            missing=data.get("missing", []),
        )
        return SimpleNamespace(
            answer=answer, chunks=[], latency_ms=int(data.get("latency_ms", 0))
        )


def citation_html(citation) -> str:
    label = f"{citation.gost}, п. {citation.clause}, с. {citation.page}"
    url = s3.url_for(citation.file, citation.page) if citation.file else ""
    if url:
        return f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'
    return html.escape(label)


def format_answer(result) -> str:
    answer = result.answer
    if answer.refused:
        text = "В корпусе нет ответа на этот вопрос."
        if answer.missing:
            text += "\nНе хватает: " + ", ".join(answer.missing)
        return html.escape(text)
    text = html.escape(answer.answer.strip())
    if answer.citations:
        lines = ["", "Источники:"]
        for citation in answer.citations:
            lines.append(f"• {citation_html(citation)}")
        text += "\n".join(lines)
    return text


def split_message(text: str, limit: int = 4000) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    current = ""
    for paragraph in text.split("\n"):
        if len(current) + len(paragraph) + 1 > limit:
            parts.append(current)
            current = paragraph
        else:
            current = f"{current}\n{paragraph}" if current else paragraph
    if current:
        parts.append(current)
    return parts


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привет! Я отвечаю на вопросы по российским стандартам ИИ (ГОСТ Р / ПНСТ).\n\n"
        "Просто задайте вопрос текстом. Я приведу цитаты: ГОСТ, пункт, страницу "
        "и ссылку на PDF с переходом на нужную страницу.\n\n"
        "Команды: /help, /gosts, /ask <вопрос>.\n"
        "База знаний: /kb <ГОСТ>, /term <термин>, /links <ГОСТ>."
    )


@dp.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Как пользоваться:\n"
        "1. Задайте вопрос по ГОСТам.\n"
        "2. Получите ответ со ссылками на пункты.\n"
        "3. Если ответа нет в корпусе — я скажу об этом.\n\n"
        "Команды: /gosts — список стандартов, /stats — статистика (админ).\n"
        "База знаний: /kb <ГОСТ> — разделы, /term <термин> — определение, "
        "/links <ГОСТ> — ссылки."
    )


@dp.message(Command("gosts"))
async def cmd_gosts(message: Message) -> None:
    path = Path(settings.data_corpus_dir) / "documents.json"
    if not path.exists():
        await message.answer("Корпус ещё не проиндексирован.")
        return
    documents = json.loads(path.read_text(encoding="utf-8"))
    lines = ["Загруженные стандарты:"]
    seen: set[str] = set()
    for doc in documents:
        key = doc["gost_number"] or doc["doc_id"]
        if key in seen:
            continue
        seen.add(key)
        lines.append(
            f"• {doc['gost_number'] or doc['doc_id']} — {(doc['title'] or '')[:80]} "
            f"({doc['chunks']} фрагментов)"
        )
    for part in split_message("\n".join(lines)):
        await message.answer(part)


@dp.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if message.from_user.id not in settings.admin_user_ids:
        await message.answer("Команда доступна только администратору.")
        return
    path = Path(settings.data_corpus_dir) / "quality_report.json"
    report = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    await message.answer(
        f"Документов: {report.get('documents_total', 0)}\n"
        f"Пунктов: {report.get('clauses_total', 0)}\n"
        f"Чанков: {report.get('chunks', {}).get('count', 0)}\n"
        f"Версия корпуса: {report.get('corpus_version', '—')}"
    )


@dp.message(Command("kb"))
async def cmd_kb(message: Message) -> None:
    if kb is None:
        await message.answer("База знаний не загружена.")
        return
    query = (message.text or "").replace("/kb", "", 1).strip()
    if not query:
        await message.answer("Использование: /kb ГОСТ Р 71484.4—2024")
        return
    outline = kb.outline(query)
    if not outline:
        await message.answer("Стандарт не найден. Посмотрите /gosts.")
        return
    lines = [f"{outline['gost']}: разделы"]
    for section in outline["sections"][:20]:
        label = section["section"] or "—"
        lines.append(f"• {label} {section['title'][:80]} — {len(section['clauses'])} п.")
    for part in split_message("\n".join(lines)):
        await message.answer(part)


@dp.message(Command("term"))
async def cmd_term(message: Message) -> None:
    if kb is None:
        await message.answer("База знаний не загружена.")
        return
    query = (message.text or "").replace("/term", "", 1).strip()
    if not query:
        await message.answer("Использование: /term граф знаний")
        return
    terms = kb.find_term(query)[:3]
    if not terms:
        await message.answer("Термин не найден в базе знаний.")
        return
    lines = []
    for term in terms:
        definition = (term.get("definition") or "").strip()
        lines.append(
            f"• {term['term']} — {term['gost']}, п. {term['clause']}, с. {term['page']}\n"
            f"{definition[:500]}"
        )
    for part in split_message("\n\n".join(lines)):
        await message.answer(part)


@dp.message(Command("links"))
async def cmd_links(message: Message) -> None:
    if kb is None:
        await message.answer("База знаний не загружена.")
        return
    query = (message.text or "").replace("/links", "", 1).strip()
    if not query:
        await message.answer("Использование: /links ГОСТ Р 71540—2024")
        return
    data = kb.neighbors(query)
    if not data["outgoing"] and not data["incoming"]:
        await message.answer("Связи для этого стандарта не найдены.")
        return
    lines = [f"{data['gost']}: связи"]
    for edge in data["outgoing"][:20]:
        mark = "в корпусе" if edge["internal"] else "внешний"
        lines.append(f"→ {edge['target']} ({mark}), п. {edge['clause']}, с. {edge['page']}")
    for edge in data["incoming"][:10]:
        lines.append(f"← {edge['source']}, п. {edge['clause']}, с. {edge['page']}")
    for part in split_message("\n".join(lines)):
        await message.answer(part)


@dp.message(Command("audit"))
async def cmd_audit(message: Message) -> None:
    if message.from_user.id not in settings.admin_user_ids:
        await message.answer("Команда доступна только администратору.")
        return
    await message.answer("Аудит ГОСТ будет реализован на этапе 8 плана.")


@dp.message(Command("ask"))
async def cmd_ask(message: Message) -> None:
    question = (message.text or "").replace("/ask", "", 1).strip()
    if not question:
        await message.answer("Напишите вопрос после /ask")
        return
    await handle_question(message, question)


@dp.message(F.text)
async def on_text(message: Message) -> None:
    await handle_question(message, (message.text or "").strip())


async def handle_question(message: Message, question: str) -> None:
    user_id = message.from_user.id
    if user_id not in settings.allowed_user_ids:
        await message.answer("Доступ к боту ограничен.")
        return
    if not hour_limiter.allow(user_id):
        await message.answer(
            f"Слишком много вопросов. Попробуйте через {hour_limiter.retry_after(user_id)} с."
        )
        return
    if not day_limiter.allow(user_id):
        await message.answer("Дневной лимит вопросов исчерпан.")
        return
    if service is None:
        await message.answer("Сервис ещё инициализируется, попробуйте через минуту.")
        return

    placeholder = await message.answer("⏳ Ищу в ГОСТах…")
    try:
        result = await service.ask(question)
        text = format_answer(result)
    except Exception as exc:  # noqa: BLE001
        text = html.escape(f"Ошибка при обработке вопроса: {exc.__class__.__name__}")
    parts = split_message(text)
    await placeholder.edit_text(parts[0], parse_mode="HTML", disable_web_page_preview=True)
    for part in parts[1:]:
        await message.answer(part, parse_mode="HTML", disable_web_page_preview=True)


async def main() -> None:
    global service
    api_url = settings.ask_api_url.strip()
    if api_url:
        service = RemoteAnswerService(api_url)
    else:
        service = AskService(
            settings,
            Path(os.getenv("DATA_CORPUS_DIR", "data/corpus")),
            Path(os.getenv("INDEX_DIR", "data/index")),
            settings.qdrant_url,
        )
    bot = Bot(token=settings.telegram_bot_token)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
