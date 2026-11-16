from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

import asyncpg
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.ask import router as ask_router
from app.audit.version import get_git_commit
from app.config import Settings, get_settings
from app.guard.rate_limit import SlidingWindowLimiter
from app.rag.service import AskService
from app.storage.s3 import S3Store
from app.web.auth import LoginRequired, attach_security_headers
from app.web.migrations import apply_migrations
from app.web.ratelimit import LoginThrottle
from app.web.store import WebStore

logger = logging.getLogger(__name__)
settings = get_settings()


def _build_service(cfg: Settings) -> AskService | None:
    index_dir = Path(os.getenv("INDEX_DIR", "data/index"))
    corpus_dir = Path(os.getenv("DATA_CORPUS_DIR", "data/corpus"))
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    if not (index_dir / "bm25.pkl").exists() or not corpus_dir.exists():
        return None
    return AskService(cfg, corpus_dir, index_dir, qdrant_url)


async def _init_web(app: FastAPI, cfg: Settings) -> None:
    try:
        pool = await asyncpg.create_pool(
            cfg.postgres_dsn, min_size=1, max_size=4, timeout=5, command_timeout=15
        )
    except Exception as exc:  # noqa: BLE001 - bot/API must survive without the web DB
        logger.warning("web disabled: postgres unavailable (%s)", exc.__class__.__name__)
        return
    try:
        if cfg.web_automigrate:
            applied = await apply_migrations(pool)
            if applied:
                logger.info("web migrations applied: %s", ", ".join(applied))
        app.state.db = pool
        app.state.web_store = WebStore(pool)
        try:
            app.state.s3 = await asyncio.wait_for(
                asyncio.to_thread(S3Store, cfg), timeout=15
            )
        except Exception as exc:  # noqa: BLE001 - PDF links are optional
            logger.warning("s3 links disabled: %s", exc.__class__.__name__)
            app.state.s3 = None
        app.state.web_ready = True
        logger.info("web ui ready")
    except Exception as exc:  # noqa: BLE001 - degraded mode instead of crash
        logger.warning("web disabled: %s", exc.__class__.__name__)
        app.state.web_store = None
        app.state.web_ready = False
        await pool.close()
        app.state.db = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg: Settings = app.state.settings
    app.state.service = None
    app.state.db = None
    app.state.web_store = None
    app.state.web_ready = False
    app.state.s3 = None
    try:
        app.state.service = _build_service(cfg)
    except Exception as exc:  # noqa: BLE001 - health must answer even if the index is broken
        logger.warning("rag service unavailable: %s", exc.__class__.__name__)
    if cfg.web_enabled:
        await _init_web(app, cfg)
    yield
    if app.state.db is not None:
        await app.state.db.close()
    if app.state.service is not None:
        await app.state.service.close()


def create_app(cfg: Settings | None = None) -> FastAPI:
    cfg = cfg or get_settings()
    app = FastAPI(title="gostrag", version=cfg.app_version, lifespan=lifespan)
    app.state.settings = cfg
    app.state.service = None
    app.state.db = None
    app.state.web_store = None
    app.state.web_ready = False
    app.state.s3 = None
    app.state.login_throttle = LoginThrottle(
        cfg.web_login_ip_limit, cfg.web_login_email_limit, cfg.web_login_window_min
    )
    app.state.web_hour_limiter = SlidingWindowLimiter(cfg.hourly_questions_per_user, 3600)
    app.state.web_day_limiter = SlidingWindowLimiter(cfg.daily_questions_per_user, 86400)
    app.state.ask_semaphore = asyncio.Semaphore(cfg.web_max_concurrent_asks)

    app.include_router(ask_router, prefix="/api")

    if cfg.web_enabled:
        from app.web.routes_admin import router as web_admin_router
        from app.web.routes_api import router as web_api_router
        from app.web.routes_chat import router as web_chat_router
        from app.web.routes_pages import router as web_pages_router
        from app.web.templating import STATIC_DIR

        app.include_router(web_pages_router)
        app.include_router(web_chat_router)
        app.include_router(web_admin_router)
        app.include_router(web_api_router, prefix="/api/web")
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

        @app.exception_handler(LoginRequired)
        async def _redirect_to_login(request: Request, exc: LoginRequired) -> RedirectResponse:
            target = exc.next_path or "/chat"
            return RedirectResponse(f"/login?next={quote(target)}", status_code=303)

    @app.middleware("http")
    async def _security_headers(request: Request, call_next):
        response = await call_next(request)
        attach_security_headers(response)
        return response

    return app


app = create_app()


@app.get("/health")
async def health() -> dict[str, str | bool]:
    cfg = app.state.settings
    service = getattr(app.state, "service", None)
    return {
        "status": "ok",
        "version": cfg.app_version,
        "commit": os.getenv("GIT_COMMIT", "") or get_git_commit(),
        "corpus_version": cfg.corpus_version,
        "collection": cfg.qdrant_collection,
        "index_ready": service is not None,
        "kb_ready": bool(service is not None and getattr(service, "kb", None) is not None),
        "web_ready": bool(getattr(app.state, "web_ready", False)),
    }
