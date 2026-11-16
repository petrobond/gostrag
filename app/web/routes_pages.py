"""HTML pages: login, logout, invite acceptance and password change."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse

from app.web.auth import (
    clear_session_cookie,
    client_ip,
    optional_user,
    require_user_api,
    require_user_page,
    rotate_csrf,
    set_session_cookie,
    verify_csrf,
)
from app.web.forms import read_payload
from app.web.security import (
    DUMMY_HASH,
    hash_password,
    is_valid_email,
    new_token,
    normalize_email,
    password_problem,
    token_hash,
    verify_password,
)
from app.web.templating import render

logger = logging.getLogger(__name__)
router = APIRouter()
INVALID_CREDENTIALS = "Неверный email или пароль."
THROTTLED = "Слишком много попыток входа. Повторите позже."


def safe_next(value: str | None) -> str:
    if not value or not value.startswith("/") or value.startswith("//"):
        return "/chat"
    return value


@router.get("/", include_in_schema=False)
async def root(request: Request):
    user = await optional_user(request)
    return RedirectResponse("/chat" if user else "/login", status_code=303)


@router.get("/me", include_in_schema=False)
async def me(request: Request) -> dict[str, str | bool]:
    user = await require_user_api(request)
    return {
        "id": user["id"],
        "email": user["email"],
        "role": user["role"],
        "must_change_password": user["must_change_password"],
    }


@router.get("/login", include_in_schema=False)
async def login_page(request: Request, next: str = "/chat"):
    if await optional_user(request):
        return RedirectResponse(safe_next(next), status_code=303)
    return render(request, "login.html", next=safe_next(next), email="", error=None)


@router.post("/login", include_in_schema=False)
async def login_submit(request: Request):
    settings = request.app.state.settings
    store = getattr(request.app.state, "web_store", None)
    payload = await read_payload(request)
    await verify_csrf(request)

    next_url = safe_next(str(payload.get("next") or "/chat"))
    email = normalize_email(str(payload.get("email") or ""))
    password = str(payload.get("password") or "")

    def failure(status_code: int, message: str):
        return render(
            request,
            "login.html",
            status_code=status_code,
            next=next_url,
            email=email,
            error=message,
        )

    if store is None:
        return failure(503, "Веб-интерфейс временно недоступен.")

    ip = client_ip(request)
    throttle = request.app.state.login_throttle
    if not await throttle.check(store, ip, email):
        return failure(429, THROTTLED)

    if not email or not is_valid_email(email):
        await throttle.fail(store, ip, email)
        return failure(401, INVALID_CREDENTIALS)

    user = await store.get_user_by_email(email)
    verified = False
    needs_rehash = False
    if user and user.get("password_hash"):
        verified, needs_rehash = await run_in_threadpool(
            verify_password, user["password_hash"], password
        )
    else:
        await run_in_threadpool(verify_password, DUMMY_HASH, password)

    if not user or not verified or not user["is_active"]:
        await throttle.fail(store, ip, email)
        logger.info("web login failed")
        return failure(401, INVALID_CREDENTIALS)

    if needs_rehash:
        await store.set_password(user["id"], await run_in_threadpool(hash_password, password))

    token = new_token()
    await store.create_session(
        user["id"],
        token_hash(token),
        datetime.now(UTC) + timedelta(days=settings.web_session_ttl_days),
        ip,
        request.headers.get("user-agent", ""),
    )
    await store.touch_login(user["id"])
    await throttle.reset(store, email)

    response = RedirectResponse(next_url, status_code=303)
    set_session_cookie(response, token, settings)
    rotate_csrf(response, settings)
    logger.info("web login ok")
    return response


@router.post("/logout", include_in_schema=False)
async def logout(request: Request):
    settings = request.app.state.settings
    await verify_csrf(request)
    user = await optional_user(request)
    store = getattr(request.app.state, "web_store", None)
    if user is not None and store is not None:
        await store.revoke_session(user["session_id"])
    response = RedirectResponse("/login", status_code=303)
    clear_session_cookie(response, settings)
    return response


async def _load_invite(request: Request, token: str):
    store = getattr(request.app.state, "web_store", None)
    if store is None:
        return None
    invite = await store.get_invite(token_hash(token))
    if not invite or invite.get("used_at") is not None:
        return None
    expires_at = invite.get("expires_at")
    if expires_at is None or expires_at <= datetime.now(UTC):
        return None
    return invite


@router.get("/invite/{token}", include_in_schema=False)
async def invite_page(request: Request, token: str):
    invite = await _load_invite(request, token)
    if invite is None:
        return render(
            request,
            "invite.html",
            status_code=404,
            token=token,
            email="",
            purpose="invite",
            invalid=True,
            error=None,
        )
    return render(
        request,
        "invite.html",
        token=token,
        email=invite["email"],
        purpose=invite["purpose"],
        invalid=False,
        error=None,
    )


@router.post("/invite/{token}", include_in_schema=False)
async def invite_submit(request: Request, token: str):
    settings = request.app.state.settings
    store = getattr(request.app.state, "web_store", None)
    payload = await read_payload(request)
    await verify_csrf(request)

    invite = await _load_invite(request, token)

    def failure(status_code: int, message: str, email: str = "", purpose: str = "invite"):
        return render(
            request,
            "invite.html",
            status_code=status_code,
            token=token,
            email=email,
            purpose=purpose,
            invalid=False,
            error=message,
        )

    if store is None:
        return failure(503, "Веб-интерфейс временно недоступен.")
    if invite is None:
        return render(
            request,
            "invite.html",
            status_code=404,
            token=token,
            email="",
            purpose="invite",
            invalid=True,
            error=None,
        )

    password = str(payload.get("password") or "")
    confirm = str(payload.get("confirm_password") or "")
    problem = password_problem(password, settings.web_password_min_len)
    if problem:
        return failure(400, problem, invite["email"], invite["purpose"])
    if password != confirm:
        return failure(400, "Пароли не совпадают.", invite["email"], invite["purpose"])

    user = await store.get_user_by_email(invite["email"])
    if user is None:
        if invite["purpose"] != "invite":
            return failure(400, "Ссылка недействительна.", invite["email"], invite["purpose"])
        user = await store.create_user(invite["email"], role=invite["role"], is_active=True)

    await store.set_password(user["id"], await run_in_threadpool(hash_password, password))
    if not user["is_active"]:
        await store.set_active(user["id"], True)
    await store.mark_invite_used(invite["id"])
    await store.revoke_user_sessions(user["id"])

    session_token = new_token()
    await store.create_session(
        user["id"],
        token_hash(session_token),
        datetime.now(UTC) + timedelta(days=settings.web_session_ttl_days),
        client_ip(request),
        request.headers.get("user-agent", ""),
    )
    await store.touch_login(user["id"])
    response = RedirectResponse("/chat", status_code=303)
    set_session_cookie(response, session_token, settings)
    rotate_csrf(response, settings)
    logger.info("web invite accepted")
    return response


@router.get("/password", include_in_schema=False)
async def password_page(request: Request):
    user = await require_user_page(request)
    return render(request, "password.html", user=user, error=None)


@router.post("/password", include_in_schema=False)
async def password_submit(request: Request):
    user = await require_user_page(request)
    settings = request.app.state.settings
    store = getattr(request.app.state, "web_store", None)
    payload = await read_payload(request)
    await verify_csrf(request)

    def failure(status_code: int, message: str):
        return render(request, "password.html", status_code=status_code, user=user, error=message)

    current = str(payload.get("current_password") or "")
    new_password = str(payload.get("new_password") or "")
    confirm = str(payload.get("confirm_password") or "")

    if store is None:
        return failure(503, "Веб-интерфейс временно недоступен.")
    db_user = await store.get_user(user["id"])
    if db_user is None or not db_user.get("password_hash"):
        return failure(400, "Пароль не задан. Обратитесь к администратору.")

    verified, _ = await run_in_threadpool(verify_password, db_user["password_hash"], current)
    if not verified:
        return failure(401, "Текущий пароль неверен.")

    problem = password_problem(new_password, settings.web_password_min_len)
    if problem:
        return failure(400, problem)
    if new_password != confirm:
        return failure(400, "Пароли не совпадают.")

    await store.set_password(user["id"], await run_in_threadpool(hash_password, new_password))
    await store.revoke_user_sessions(user["id"], keep_session_id=user["session_id"])
    logger.info("web password changed")
    return RedirectResponse("/chat?password=1", status_code=303)
