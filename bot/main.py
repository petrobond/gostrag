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
from app.kb.formatting import format_outline
from app.kb.kb import KnowledgeBase  # noqa: E402
from app.rag.service import AskService  # noqa: E402
from app.storage.s3 import S3Store  # noqa: E402
from app.storage.usage import UsageStore  # noqa: E402

settings = get_settings()
dp = Dispatcher()
hour_limiter = SlidingWindowLimiter(settings.hourly_questions_per_user, 3600)
day_limiter = SlidingWindowLimiter(settings.daily_questions_per_user, 86400)
service: AskService | None = None
usage: UsageStore | None = None
audit_tasks: dict[int, asyncio.subprocess.Process] = {}
APP_DIR = Path(__file__).resolve().parents[1]
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
        "Команды: /help, /gosts, /ask <вопрос>, /audit (whitelist).\n"
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
        "Аудит: /audit — ГОСТ-аудит версии (whitelist/админ), /audit_status — статус.\n"
        "База знаний: /kb <ГОСТ> — разделы, /term <термин> — определение, "
        "/links <ГОСТ> — ссылки. «п.» — пункт стандарта."
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
    if usage is not None:
        try:
            stats = await usage.stats(days=30)
            await message.answer(
                f"Вопросов: {stats.get('questions', 0)}\n"
                f"Отказов: {stats.get('refusals', 0)}\n"
                f"Пользователей: {stats.get('users', 0)}\n"
                f"p50 / p95: {stats.get('p50', 0)} / {stats.get('p95', 0)} мс\n"
                f"Токены: {stats.get('tokens_in', 0)} / {stats.get('tokens_out', 0)}"
            )
            return
        except Exception as exc:  # noqa: BLE001
            await message.answer(f"Статистика PostgreSQL недоступна: {exc.__class__.__name__}")
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
    lines = format_outline(outline)
    for part in split_message(lines):
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


def _audit_summary(manifest_path: Path) -> str:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    return (
        f"Аудит {data.get('product_version')} готов:\n"
        f"Coverage: {float(data.get('coverage', 0)):.1%}\n"
        f"Compliance (применимые): {float(data.get('compliance_applicable', 0)):.1%}\n"
        f"Требований: {data.get('requirements_total')}\n"
        f"Файл: {data.get('md_path')}"
    )


async def _notify_audit(
    chat_id: int,
    bot: Bot,
    user_id: int,
    process: asyncio.subprocess.Process,
    manifest_path: Path,
) -> None:
    output, _ = await process.communicate()
    audit_tasks.pop(user_id, None)
    if process.returncode == 0 and manifest_path.exists():
        try:
            text = _audit_summary(manifest_path)
        except Exception:  # noqa: BLE001
            text = "Аудит завершён, но manifest.json не прочитан."
    else:
        tail = output.decode(errors="ignore")[-800:]
        text = f"Аудит завершился ошибкой (код {process.returncode}).\n{tail}"
    await bot.send_message(chat_id=chat_id, text=text[:4000])


@dp.message(Command("audit"))
async def cmd_audit(message: Message) -> None:
    user_id = message.from_user.id
    allowed = settings.allowed_user_ids | settings.admin_user_ids
    if user_id not in allowed:
        await message.answer("Команда доступна только whitelist/администратору.")
        return
    manifest_path = Path(settings.reports_dir) / settings.app_version / str(user_id) / "manifest.json"
    if manifest_path.exists():
        await message.answer(_audit_summary(manifest_path))
        return
    process = audit_tasks.get(user_id)
    if process is not None and process.returncode is None:
        await message.answer("Аудит уже выполняется.")
        return
    await message.answer("Запускаю аудит ГОСТов. Это займёт несколько минут.")
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "scripts/audit.py",
        "--requirements",
        "eval/requirements.yaml",
        "--reports",
        settings.reports_dir,
        "--user-id",
        str(user_id),
        cwd=str(APP_DIR),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    audit_tasks[user_id] = process
    asyncio.create_task(
        _notify_audit(message.chat.id, message.bot, user_id, process, manifest_path)
    )


@dp.message(Command("audit_status"))
async def cmd_audit_status(message: Message) -> None:
    user_id = message.from_user.id
    manifest_path = Path(settings.reports_dir) / settings.app_version / str(user_id) / "manifest.json"
    if manifest_path.exists():
        await message.answer(_audit_summary(manifest_path))
        return
    process = audit_tasks.get(user_id)
    if process is not None and process.returncode is None:
        await message.answer("Аудит выполняется.")
        return
    await message.answer("Аудит для этой версии ещё не запускался.")


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
        if usage is not None:
            try:
                answer = result.answer
                await usage.log(
                    user_id,
                    question,
                    str(getattr(answer, "answer", "")),
                    [
                        {
                            "gost": getattr(citation, "gost", ""),
                            "clause": getattr(citation, "clause", ""),
                            "page": getattr(citation, "page", 0),
                        }
                        for citation in getattr(answer, "citations", [])
                    ],
                    bool(getattr(answer, "refused", False)),
                    int(getattr(result, "latency_ms", 0) or 0),
                    str(getattr(answer, "model", "")),
                    int(getattr(answer, "tokens_in", 0) or 0),
                    int(getattr(answer, "tokens_out", 0) or 0),
                )
            except Exception:  # noqa: BLE001 - usage must not break answers
                pass
        text = format_answer(result)
    except Exception as exc:  # noqa: BLE001
        text = html.escape(f"Ошибка при обработке вопроса: {exc.__class__.__name__}")
    parts = split_message(text)
    await placeholder.edit_text(parts[0], parse_mode="HTML", disable_web_page_preview=True)
    for part in parts[1:]:
        await message.answer(part, parse_mode="HTML", disable_web_page_preview=True)


async def main() -> None:
    global service, usage
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
    usage = UsageStore(settings.postgres_dsn)
    try:
        await usage.connect()
    except Exception:  # noqa: BLE001 - bot works without usage DB
        usage = None
    bot = Bot(token=settings.telegram_bot_token)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
