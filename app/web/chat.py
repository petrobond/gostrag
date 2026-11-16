"""Web chat orchestration: one AskService, conversations and citations."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict
from typing import Any

from fastapi import HTTPException

logger = logging.getLogger(__name__)

DEFAULT_TITLE = "Новый диалог"
MAX_QUESTION = 1000


class ConversationNotFound(Exception):
    """Raised when a conversation does not exist or belongs to another user."""


class ServiceUnavailable(Exception):
    """Raised when the RAG service is missing or failed."""


def clean_question(value: Any) -> str:
    return " ".join(str(value or "").split())


def conversation_title(question: str) -> str:
    return question[:80] + ("…" if len(question) > 80 else "")


def citations_payload(citations, s3) -> list[dict]:
    payload: list[dict] = []
    for citation in citations:
        item = asdict(citation)
        url = ""
        if s3 is not None and citation.file:
            try:
                url = s3.url_for(citation.file, citation.page)
            except Exception:  # noqa: BLE001 - a broken S3 must not break answers
                url = ""
        item["pdf_url"] = url
        payload.append(item)
    return payload


def parse_citations(value: Any) -> list[dict]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def serialize_conversation(conversation: dict) -> dict:
    payload = {
        "id": str(conversation["id"]),
        "title": conversation.get("title") or DEFAULT_TITLE,
        "created_at": conversation["created_at"].isoformat(),
        "updated_at": conversation["updated_at"].isoformat(),
    }
    if "messages" in conversation:
        payload["messages"] = int(conversation["messages"])
    return payload


def serialize_message(message: dict) -> dict:
    return {
        "id": str(message["id"]),
        "role": message["role"],
        "content": message["content"],
        "citations": parse_citations(message.get("citations_json")),
        "refused": bool(message.get("refused")),
        "latency_ms": message.get("latency_ms"),
        "model": message.get("model"),
        "created_at": message["created_at"].isoformat(),
    }


def _too_many(retry_after: int = 60) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail="rate limit exceeded",
        headers={"Retry-After": str(max(1, retry_after))},
    )


def _check_limits(state, user_id: str) -> None:
    if not state.web_hour_limiter.allow(user_id):
        raise _too_many(state.web_hour_limiter.retry_after(user_id))
    if not state.web_day_limiter.allow(user_id):
        raise _too_many(state.web_day_limiter.retry_after(user_id))


async def ask_and_store(
    state,
    *,
    user_id: str,
    question: str,
    conversation_id: str | None = None,
    top_k: int | None = None,
) -> dict:
    if not question or len(question) < 3 or len(question) > MAX_QUESTION:
        raise HTTPException(status_code=422, detail="question must be 3..1000 characters")

    store = state.web_store
    service = state.service
    if store is None:
        raise ServiceUnavailable("web store is not ready")
    if service is None:
        raise ServiceUnavailable("index is not ready")

    existing = None
    if conversation_id:
        existing = await store.get_conversation(conversation_id, user_id)
        if existing is None:
            raise ConversationNotFound

    _check_limits(state, user_id)
    semaphore = state.ask_semaphore
    if semaphore.locked():
        raise _too_many(5)

    async with semaphore:
        try:
            result = await asyncio.wait_for(
                service.ask(question, top_k=top_k),
                timeout=state.settings.request_timeout_sec + 30,
            )
        except TimeoutError as exc:
            raise ServiceUnavailable("answer timed out") from exc
        except Exception as exc:  # noqa: BLE001 - UI shows a retry, process stays alive
            logger.warning("web ask failed: %s", exc.__class__.__name__)
            raise ServiceUnavailable("answer failed") from exc

    if existing is None:
        existing = await store.create_conversation(user_id, conversation_title(question))
    user_message = await store.add_message(existing["id"], "user", question)
    answer = result.answer
    citations = citations_payload(answer.citations, state.s3)
    assistant_message = await store.add_message(
        existing["id"],
        "assistant",
        answer.answer,
        citations_json=citations,
        refused=answer.refused,
        latency_ms=result.latency_ms,
        model=answer.model or None,
    )
    await store.touch_conversation(existing["id"])

    return {
        "conversation_id": str(existing["id"]),
        "message_id": str(assistant_message["id"]),
        "user_message_id": str(user_message["id"]),
        "answer": answer.answer,
        "citations": citations,
        "refused": answer.refused,
        "general_knowledge": answer.general_knowledge,
        "missing": answer.missing,
        "confidence": answer.confidence,
        "model": answer.model,
        "provider": answer.provider,
        "latency_ms": result.latency_ms,
        "chunks": [
            {
                "chunk_id": chunk.chunk_id,
                "gost": chunk.gost_number,
                "clause": chunk.clause,
                "page": chunk.page,
                "score": chunk.score,
            }
            for chunk in result.chunks
        ],
    }
