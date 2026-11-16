"""Cookie sessions, CSRF protection and access dependencies for the web UI."""

from __future__ import annotations

import ipaddress
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, Request, Response

from app.config import Settings
from app.web.forms import read_payload
from app.web.security import constant_time_equals, new_token, token_hash

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; "
        "script-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    ),
}


class LoginRequired(Exception):
    """Raised by page handlers when there is no valid session."""

    def __init__(self, next_path: str = "/chat") -> None:
        self.next_path = next_path


def settings_of(request: Request) -> Settings:
    return request.app.state.settings


def cookie_names(secure: bool) -> tuple[str, str]:
    prefix = "__Host-" if secure else ""
    return f"{prefix}gostrag_sid", f"{prefix}gostrag_csrf"


def client_ip(request: Request) -> str:
    host = request.client.host if request.client else ""
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return ""
    return host


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


async def optional_user(request: Request) -> dict[str, Any] | None:
    store = getattr(request.app.state, "web_store", None)
    if store is None:
        return None

    settings = settings_of(request)
    sid_name, _ = cookie_names(settings.web_cookie_secure)
    raw_token = request.cookies.get(sid_name)
    if not raw_token:
        return None

    session = await store.get_session(token_hash(raw_token))
    if not session or session.get("revoked_at") is not None or not session.get("is_active"):
        return None

    now = datetime.now(UTC)
    expires_at = _aware(session.get("expires_at"))
    last_seen = _aware(session.get("last_seen_at")) or now
    if expires_at is None or expires_at <= now:
        return None
    if last_seen + timedelta(hours=settings.web_session_idle_hours) <= now:
        await store.revoke_session(session["session_id"])
        return None

    await store.touch_session(session["session_id"])
    return {
        "id": str(session["user_id"]),
        "email": session["email"],
        "role": session["role"],
        "is_active": session["is_active"],
        "must_change_password": session["must_change_password"],
        "session_id": str(session["session_id"]),
    }


async def require_user_api(request: Request) -> dict[str, Any]:
    user = await optional_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return user


async def require_admin_api(request: Request) -> dict[str, Any]:
    user = await require_user_api(request)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="admin access required")
    return user


async def require_user_page(request: Request) -> dict[str, Any]:
    user = await optional_user(request)
    if user is None:
        raise LoginRequired(request.url.path)
    return user


async def require_admin_page(request: Request) -> dict[str, Any]:
    user = await require_user_page(request)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="admin access required")
    return user


def _cookie_kwargs(settings: Settings) -> dict[str, Any]:
    return {
        "max_age": settings.web_session_ttl_days * 86400,
        "secure": settings.web_cookie_secure,
        "samesite": "lax",
        "path": "/",
    }


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    sid_name, _ = cookie_names(settings.web_cookie_secure)
    response.set_cookie(sid_name, token, httponly=True, **_cookie_kwargs(settings))


def clear_session_cookie(response: Response, settings: Settings) -> None:
    sid_name, _ = cookie_names(settings.web_cookie_secure)
    kwargs = _cookie_kwargs(settings)
    response.delete_cookie(
        sid_name,
        httponly=True,
        secure=kwargs["secure"],
        samesite=kwargs["samesite"],
        path=kwargs["path"],
    )


def current_or_new_csrf(request: Request) -> str:
    settings = settings_of(request)
    _, csrf_name = cookie_names(settings.web_cookie_secure)
    return request.cookies.get(csrf_name) or new_token(24)


def apply_csrf_cookie(request: Request, response: Response, token: str) -> None:
    settings = settings_of(request)
    _, csrf_name = cookie_names(settings.web_cookie_secure)
    if request.cookies.get(csrf_name) == token:
        return
    response.set_cookie(csrf_name, token, httponly=False, **_cookie_kwargs(settings))


def rotate_csrf(response: Response, settings: Settings, token: str | None = None) -> None:
    _, csrf_name = cookie_names(settings.web_cookie_secure)
    response.set_cookie(
        csrf_name, token or new_token(24), httponly=False, **_cookie_kwargs(settings)
    )


async def verify_csrf(request: Request) -> None:
    settings = settings_of(request)
    _, csrf_name = cookie_names(settings.web_cookie_secure)
    cookie = request.cookies.get(csrf_name, "")
    payload = await read_payload(request)
    submitted = request.headers.get("x-csrf-token") or str(payload.get("csrf_token") or "")
    if not cookie or not submitted or not constant_time_equals(cookie, submitted):
        raise HTTPException(status_code=403, detail="csrf check failed")
    site = request.headers.get("sec-fetch-site")
    if site and site not in ("same-origin", "none"):
        raise HTTPException(status_code=403, detail="cross-site request blocked")


def attach_security_headers(response: Response) -> None:
    for header, value in SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
