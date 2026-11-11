from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    top_k: int = Field(default=6, ge=1, le=10)


@router.post("/ask")
async def ask(payload: AskRequest, request: Request) -> dict:
    service = getattr(request.app.state, "service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="index is not ready")
    result = await service.ask(payload.question, top_k=payload.top_k)
    return {
        "answer": result.answer.answer,
        "citations": [asdict(citation) for citation in result.answer.citations],
        "refused": result.answer.refused,
        "general_knowledge": result.answer.general_knowledge,
        "missing": result.answer.missing,
        "confidence": result.answer.confidence,
        "model": result.answer.model,
        "provider": result.answer.provider,
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
