"""JSON API for the web UI: conversations, ask and admin stats."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from app.web.auth import require_admin_api, require_user_api, verify_csrf
from app.web.chat import (
    DEFAULT_TITLE,
    ConversationNotFound,
    ServiceUnavailable,
    ask_and_store,
    clean_question,
    serialize_conversation,
    serialize_message,
)
from app.web.forms import read_payload

router = APIRouter()


def _store(request: Request):
    store = getattr(request.app.state, "web_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="web store is not ready")
    return store


@router.get("/conversations")
async def list_conversations(request: Request) -> dict:
    user = await require_user_api(request)
    conversations = await _store(request).list_conversations(user["id"])
    return {"conversations": [serialize_conversation(item) for item in conversations]}


@router.post("/conversations", status_code=201)
async def create_conversation(request: Request) -> dict:
    user = await require_user_api(request)
    await verify_csrf(request)
    payload = await read_payload(request)
    title = str(payload.get("title") or DEFAULT_TITLE)[:200] or DEFAULT_TITLE
    conversation = await _store(request).create_conversation(user["id"], title)
    return serialize_conversation(conversation)


@router.get("/conversations/{conversation_id}")
async def get_conversation(request: Request, conversation_id: str) -> dict:
    user = await require_user_api(request)
    store = _store(request)
    conversation = await store.get_conversation(conversation_id, user["id"])
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    messages = await store.list_messages(conversation["id"])
    return {
        **serialize_conversation(conversation),
        "messages": [serialize_message(message) for message in messages],
    }


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(request: Request, conversation_id: str) -> Response:
    user = await require_user_api(request)
    await verify_csrf(request)
    deleted = await _store(request).delete_conversation(conversation_id, user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="conversation not found")
    return Response(status_code=204)


@router.post("/ask")
async def ask(request: Request) -> dict:
    user = await require_user_api(request)
    await verify_csrf(request)
    payload = await read_payload(request)

    question = clean_question(payload.get("question"))
    conversation_id = str(payload.get("conversation_id") or "") or None
    top_k = payload.get("top_k")
    if top_k in (None, ""):
        top_k_value = None
    else:
        try:
            top_k_value = int(top_k)
        except (TypeError, ValueError):
            top_k_value = None
        if top_k_value is not None and not 1 <= top_k_value <= 10:
            top_k_value = None

    try:
        return await ask_and_store(
            request.app.state,
            user_id=user["id"],
            question=question,
            conversation_id=conversation_id,
            top_k=top_k_value,
        )
    except ConversationNotFound as exc:
        raise HTTPException(status_code=404, detail="conversation not found") from exc
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=502, detail="answer is unavailable") from exc


@router.get("/admin/stats")
async def admin_stats(request: Request) -> dict:
    await require_admin_api(request)
    store = _store(request)
    stats = await store.web_stats(days=30)
    settings = request.app.state.settings
    stats.update(
        {
            "corpus_version": settings.corpus_version,
            "collection": settings.qdrant_collection,
            "index_ready": request.app.state.service is not None,
            "web_ready": bool(getattr(request.app.state, "web_ready", False)),
        }
    )
    return stats
