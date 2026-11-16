"""HTML chat pages: history, thread rendering and HTMX form posts."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.web.auth import require_user_page, verify_csrf
from app.web.chat import (
    DEFAULT_TITLE,
    ConversationNotFound,
    ServiceUnavailable,
    ask_and_store,
    clean_question,
    parse_citations,
)
from app.web.forms import read_payload
from app.web.templating import render

logger = logging.getLogger(__name__)
router = APIRouter()

BUSY = "Сервис ответов перегружен. Попробуйте ещё раз через минуту."
UNAVAILABLE = "Сервис ответов недоступен. Попробуйте ещё раз."
RATE_LIMITED = "Слишком много вопросов. Подождите немного."


def _is_htmx(request: Request) -> bool:
    return request.headers.get("hx-request", "").lower() == "true"


async def _context(request: Request, user: dict, conversation_id: str | None = None):
    store = getattr(request.app.state, "web_store", None)
    if store is None:
        return None
    conversations = await store.list_conversations(user["id"])
    conversation = None
    messages: list[dict] = []
    if conversation_id:
        conversation = await store.get_conversation(conversation_id, user["id"])
        if conversation is None:
            return None
        messages = await store.list_messages(conversation["id"])
        for message in messages:
            message["citations"] = parse_citations(message.get("citations_json"))
    return {
        "conversations": conversations,
        "conversation": conversation,
        "messages": messages,
    }


def _unavailable_page(request: Request, user: dict):
    return render(
        request,
        "chat.html",
        status_code=503,
        user=user,
        conversations=[],
        conversation=None,
        messages=[],
        question="",
        error="Веб-интерфейс временно недоступен.",
    )


@router.get("/chat")
async def chat_index(request: Request):
    user = await require_user_page(request)
    context = await _context(request, user)
    if context is None:
        return _unavailable_page(request, user)
    return render(request, "chat.html", user=user, question="", error=None, **context)


@router.get("/chat/{conversation_id}")
async def chat_page(request: Request, conversation_id: str):
    user = await require_user_page(request)
    context = await _context(request, user, conversation_id)
    if context is None:
        return render(request, "errors/404.html", status_code=404, user=user)
    return render(request, "chat.html", user=user, question="", error=None, **context)


async def _failed(
    request: Request,
    user: dict,
    conversation_id: str | None,
    question: str,
    message: str,
    status_code: int,
    htmx: bool,
):
    context = await _context(request, user, conversation_id)
    if context is None:
        context = {"conversations": [], "conversation": None, "messages": []}
    template = "partials/chat_update.html" if htmx else "chat.html"
    return render(
        request,
        template,
        status_code=status_code,
        user=user,
        question=question,
        error=message,
        **context,
    )


@router.post("/web/ask")
async def chat_ask(request: Request):
    user = await require_user_page(request)
    await verify_csrf(request)
    payload = await read_payload(request)

    question = clean_question(payload.get("question"))
    conversation_id = str(payload.get("conversation_id") or "") or None
    htmx = _is_htmx(request)

    try:
        result = await ask_and_store(
            request.app.state,
            user_id=user["id"],
            question=question,
            conversation_id=conversation_id,
        )
    except ConversationNotFound:
        return render(request, "errors/404.html", status_code=404, user=user)
    except ServiceUnavailable:
        return await _failed(request, user, conversation_id, question, UNAVAILABLE, 200 if htmx else 502, htmx)
    except HTTPException as exc:
        if exc.status_code == 429:
            return await _failed(request, user, conversation_id, question, RATE_LIMITED, 200 if htmx else 429, htmx)
        if exc.status_code == 422:
            message = "Вопрос должен быть от 3 до 1000 символов."
            return await _failed(request, user, conversation_id, question, message, 200 if htmx else 422, htmx)
        raise

    context = await _context(request, user, result["conversation_id"])
    if context is None:
        return render(request, "errors/404.html", status_code=404, user=user)
    if htmx:
        return render(
            request,
            "partials/chat_update.html",
            user=user,
            question="",
            error=None,
            **context,
        )
    return RedirectResponse(f"/chat/{result['conversation_id']}", status_code=303)


@router.post("/web/conversations/new")
async def new_conversation(request: Request):
    user = await require_user_page(request)
    await verify_csrf(request)
    store = getattr(request.app.state, "web_store", None)
    if store is None:
        return _unavailable_page(request, user)
    conversation = await store.create_conversation(user["id"], DEFAULT_TITLE)
    return RedirectResponse(f"/chat/{conversation['id']}", status_code=303)


@router.post("/web/conversations/{conversation_id}/delete")
async def delete_conversation_page(request: Request, conversation_id: str):
    user = await require_user_page(request)
    await verify_csrf(request)
    store = getattr(request.app.state, "web_store", None)
    if store is None:
        return _unavailable_page(request, user)
    if not await store.delete_conversation(conversation_id, user["id"]):
        return render(request, "errors/404.html", status_code=404, user=user)
    return RedirectResponse("/chat", status_code=303)
