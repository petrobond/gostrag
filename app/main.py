from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.api.ask import router as ask_router
from app.config import get_settings
from app.rag.service import AskService

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    index_dir = Path(os.getenv("INDEX_DIR", "data/index"))
    corpus_dir = Path(os.getenv("DATA_CORPUS_DIR", "data/corpus"))
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    if (index_dir / "bm25.pkl").exists() and corpus_dir.exists():
        app.state.service = AskService(settings, corpus_dir, index_dir, qdrant_url)
    else:
        app.state.service = None
    yield
    if app.state.service is not None:
        await app.state.service.close()


app = FastAPI(title="gostrag", version=settings.app_version, lifespan=lifespan)
app.include_router(ask_router, prefix="/api")


@app.get("/health")
async def health() -> dict[str, str | bool]:
    ready = getattr(app.state, "service", None) is not None
    return {
        "status": "ok",
        "version": settings.app_version,
        "corpus_version": settings.corpus_version,
        "index_ready": ready,
    }
