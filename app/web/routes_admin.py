"""Admin pages: stats, users/invites, read-only documents and audit reports."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from app.web.auth import require_user_page, verify_csrf
from app.web.forms import read_payload
from app.web.security import is_valid_email, new_token, normalize_email, token_hash
from app.web.templating import render

logger = logging.getLogger(__name__)
router = APIRouter()

AUDIT_ROOTS = ("reports", "docs")
MAX_AUDIT_BYTES = 512 * 1024


def _forbidden(request: Request, user: dict):
    return render(request, "errors/403.html", status_code=403, user=user)


def _base_url(request: Request) -> str:
    settings = request.app.state.settings
    if settings.web_domain:
        return f"https://{settings.web_domain}"
    return str(request.base_url).rstrip("/")


def _store(request: Request):
    return getattr(request.app.state, "web_store", None)


def _audit_root(settings, name: str) -> Path | None:
    if name == "reports":
        return Path(settings.reports_dir)
    if name == "docs":
        return Path("docs/reports")
    return None


def _collect_audit(settings) -> list[dict]:
    items: list[dict] = []
    for name in AUDIT_ROOTS:
        root = _audit_root(settings, name)
        if root is None or not root.is_dir():
            continue
        for file in sorted(root.rglob("*")):
            if not file.is_file() or file.suffix.lower() not in {".md", ".json"}:
                continue
            stat = file.stat()
            items.append(
                {
                    "root": name,
                    "path": str(file.relative_to(root)),
                    "size": stat.st_size,
                    "mtime": datetime.fromtimestamp(stat.st_mtime, UTC),
                }
            )
    return items


@router.get("/admin")
async def dashboard(request: Request):
    user = await require_user_page(request)
    if user["role"] != "admin":
        return _forbidden(request, user)
    store = _store(request)
    stats = await store.web_stats(days=30) if store is not None else {}
    usage = getattr(request.app.state, "usage", None)
    telegram_stats: dict = {}
    if usage is not None:
        try:
            telegram_stats = await usage.stats(days=30)
        except Exception:  # noqa: BLE001 - bot stats are optional
            telegram_stats = {}
    settings = request.app.state.settings
    return render(
        request,
        "admin/dashboard.html",
        user=user,
        stats=stats,
        telegram_stats=telegram_stats,
        corpus_version=settings.corpus_version,
        collection=settings.qdrant_collection,
        index_ready=request.app.state.service is not None,
        web_ready=bool(getattr(request.app.state, "web_ready", False)),
    )


async def _users_page(
    request: Request,
    user: dict,
    *,
    invite_url: str | None = None,
    reset_url: str | None = None,
    error: str | None = None,
    status_code: int = 200,
):
    store = _store(request)
    users = await store.list_users() if store is not None else []
    return render(
        request,
        "admin/users.html",
        status_code=status_code,
        user=user,
        users=users,
        invite_url=invite_url,
        reset_url=reset_url,
        error=error,
    )


@router.get("/admin/users")
async def users_page(request: Request):
    user = await require_user_page(request)
    if user["role"] != "admin":
        return _forbidden(request, user)
    return await _users_page(request, user)


@router.post("/admin/users/invite")
async def create_invite(request: Request):
    user = await require_user_page(request)
    if user["role"] != "admin":
        return _forbidden(request, user)
    await verify_csrf(request)
    payload = await read_payload(request)

    email = normalize_email(str(payload.get("email") or ""))
    store = _store(request)
    if store is None:
        return await _users_page(request, user, error="Хранилище недоступно.", status_code=503)
    if not is_valid_email(email):
        return await _users_page(request, user, error="Укажите корректный email.", status_code=400)
    if await store.get_user_by_email(email) is not None:
        return await _users_page(
            request, user, error="Пользователь с таким email уже существует.", status_code=400
        )

    settings = request.app.state.settings
    token = new_token()
    await store.create_invite(
        email,
        "user",
        "invite",
        token_hash(token),
        user["id"],
        datetime.now(UTC) + timedelta(days=settings.web_invite_ttl_days),
    )
    logger.info("web invite issued")
    return await _users_page(request, user, invite_url=f"{_base_url(request)}/invite/{token}")


@router.post("/admin/users/{target_id}/reset")
async def issue_password_reset(request: Request, target_id: str):
    user = await require_user_page(request)
    if user["role"] != "admin":
        return _forbidden(request, user)
    await verify_csrf(request)

    store = _store(request)
    target = await store.get_user(target_id) if store is not None else None
    if target is None:
        return render(request, "errors/404.html", status_code=404, user=user)

    settings = request.app.state.settings
    token = new_token()
    await store.create_invite(
        target["email"],
        target["role"],
        "reset",
        token_hash(token),
        user["id"],
        datetime.now(UTC) + timedelta(days=settings.web_invite_ttl_days),
    )
    logger.info("web password reset issued")
    return await _users_page(
        request, user, reset_url=f"{_base_url(request)}/invite/{token}"
    )


async def _set_active(request: Request, target_id: str, active: bool):
    user = await require_user_page(request)
    if user["role"] != "admin":
        return _forbidden(request, user)
    await verify_csrf(request)

    store = _store(request)
    target = await store.get_user(target_id) if store is not None else None
    if target is None:
        return render(request, "errors/404.html", status_code=404, user=user)
    if str(target["id"]) == user["id"] and not active:
        return await _users_page(
            request,
            user,
            error="Нельзя заблокировать собственную учётную запись.",
            status_code=400,
        )
    await store.set_active(target["id"], active)
    logger.info("web user status changed")
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/admin/users/{target_id}/block")
async def block_user(request: Request, target_id: str):
    return await _set_active(request, target_id, False)


@router.post("/admin/users/{target_id}/unblock")
async def unblock_user(request: Request, target_id: str):
    return await _set_active(request, target_id, True)


@router.get("/admin/documents")
async def documents_page(request: Request):
    user = await require_user_page(request)
    if user["role"] != "admin":
        return _forbidden(request, user)

    settings = request.app.state.settings
    corpus = Path(settings.data_corpus_dir) / "documents.json"
    documents: list[dict] = []
    error = None
    if corpus.is_file():
        try:
            parsed = json.loads(corpus.read_text(encoding="utf-8"))
            if isinstance(parsed, list):
                documents = [doc for doc in parsed if isinstance(doc, dict)]
        except json.JSONDecodeError:
            error = "Не удалось прочитать documents.json."
    else:
        error = f"Файл {corpus} не найден."

    s3 = getattr(request.app.state, "s3", None)
    for doc in documents:
        filename = str(doc.get("filename") or "")
        doc["pdf_url"] = s3.url_for(filename, 1) if (s3 is not None and filename) else ""

    return render(
        request,
        "admin/documents.html",
        user=user,
        documents=documents,
        corpus_path=str(corpus),
        error=error,
    )


@router.get("/admin/audit")
async def audit_page(request: Request):
    user = await require_user_page(request)
    if user["role"] != "admin":
        return _forbidden(request, user)
    settings = request.app.state.settings
    from app.web.tool_data import ToolService

    summary = ToolService(
        settings,
        service=getattr(request.app.state, "service", None),
        s3=getattr(request.app.state, "s3", None),
    ).latest_audit()
    return render(
        request,
        "admin/audit.html",
        user=user,
        items=_collect_audit(settings),
        summary=summary,
        error=None,
    )


@router.get("/admin/audit/view")
async def audit_view(request: Request, root: str = "reports", path: str = ""):
    user = await require_user_page(request)
    if user["role"] != "admin":
        return _forbidden(request, user)

    settings = request.app.state.settings
    base = _audit_root(settings, root)
    if base is None or not base.is_dir():
        return render(request, "errors/404.html", status_code=404, user=user)

    base_resolved = base.resolve()
    candidate = (base / path).resolve()
    if not candidate.is_relative_to(base_resolved) or not candidate.is_file():
        return render(request, "errors/404.html", status_code=404, user=user)
    if candidate.stat().st_size > MAX_AUDIT_BYTES:
        return render(
            request,
            "admin/audit.html",
            status_code=413,
            user=user,
            items=_collect_audit(settings),
            error="Файл слишком большой для просмотра.",
        )

    content = candidate.read_text(encoding="utf-8", errors="replace")
    return render(
        request,
        "admin/audit_view.html",
        user=user,
        title=f"{root}/{path}",
        content=content,
    )
