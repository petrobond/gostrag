"""Jinja2 environment and page rendering helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.web.auth import apply_csrf_cookie, current_or_new_csrf

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def format_dt(value: Any) -> str:
    if not value:
        return "—"
    if isinstance(value, str):
        return value
    if not isinstance(value, datetime):
        return str(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone().strftime("%d.%m.%Y %H:%M")


templates.env.filters["dt"] = format_dt


def render(
    request: Request,
    name: str,
    *,
    status_code: int = 200,
    user: dict[str, Any] | None = None,
    **context: Any,
):
    settings = request.app.state.settings
    csrf_token = current_or_new_csrf(request)
    response = templates.TemplateResponse(
        request=request,
        name=name,
        context={
            "user": user,
            "csrf_token": csrf_token,
            "app_version": settings.app_version,
            "corpus_version": settings.corpus_version,
            "web_domain": settings.web_domain,
            **context,
        },
        status_code=status_code,
    )
    response.headers.setdefault("Cache-Control", "no-store")
    apply_csrf_cookie(request, response, csrf_token)
    return response
