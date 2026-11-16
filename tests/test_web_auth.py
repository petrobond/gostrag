import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from web_support import build_app, csrf_token, login, start

from app.web.security import token_hash


def test_guest_redirected_to_login(monkeypatch):
    client, _, _ = build_app(monkeypatch)
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    response = client.get("/password", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_guest_me_returns_401(monkeypatch):
    client, _, _ = build_app(monkeypatch)
    assert client.get("/me").status_code == 401


def test_login_sets_http_only_cookie_and_me_works(monkeypatch):
    client, store, _ = build_app(monkeypatch)
    store.add_user("user@example.ru")

    response = login(client, "user@example.ru")
    assert response.status_code == 303
    assert response.headers["location"] == "/chat"

    set_cookie = response.headers["set-cookie"]
    assert "gostrag_sid=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie

    me = client.get("/me")
    assert me.status_code == 200
    payload = me.json()
    assert payload["email"] == "user@example.ru"
    assert payload["role"] == "user"


def test_secure_cookie_uses_host_prefix(monkeypatch):
    client, store, _ = build_app(monkeypatch, secure=True)
    store.add_user("admin@example.ru", role="admin")

    response = login(client, "admin@example.ru")
    assert response.status_code == 303
    set_cookie = response.headers["set-cookie"]
    assert "__Host-gostrag_sid=" in set_cookie
    assert "Secure" in set_cookie
    assert "HttpOnly" in set_cookie
    assert client.get("/me").status_code == 200


def test_login_rejects_wrong_password(monkeypatch):
    client, store, _ = build_app(monkeypatch)
    store.add_user("user@example.ru")

    response = login(client, "user@example.ru", "wrong password")
    assert response.status_code == 401
    assert "Неверный email или пароль" in response.text
    assert "gostrag_sid" not in client.cookies


def test_login_requires_csrf(monkeypatch):
    client, store, _ = build_app(monkeypatch)
    store.add_user("user@example.ru")
    client.get("/login")

    missing = client.post(
        "/login", data={"email": "user@example.ru", "password": "correct horse battery"}
    )
    assert missing.status_code == 403

    wrong = client.post(
        "/login",
        data={
            "email": "user@example.ru",
            "password": "correct horse battery",
            "csrf_token": "wrong-token",
        },
    )
    assert wrong.status_code == 403


def test_logout_revokes_session(monkeypatch):
    client, store, _ = build_app(monkeypatch)
    store.add_user("user@example.ru")
    login(client, "user@example.ru")
    assert client.get("/me").status_code == 200

    response = client.post(
        "/logout", data={"csrf_token": csrf_token(client)}, follow_redirects=False
    )
    assert response.status_code == 303
    assert client.get("/me").status_code == 401


def test_invite_acceptance_and_single_use(monkeypatch):
    client, store, _ = build_app(monkeypatch)
    token = "invite-token-value"
    asyncio.run(
        store.create_invite(
            "new@example.ru",
            "user",
            "invite",
            token_hash(token),
            None,
            datetime.now(UTC) + timedelta(days=1),
        )
    )

    page = client.get(f"/invite/{token}")
    assert page.status_code == 200
    assert "new@example.ru" in page.text

    response = client.post(
        f"/invite/{token}",
        data={
            "password": "brand new password",
            "confirm_password": "brand new password",
            "csrf_token": csrf_token(client),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert client.get("/me").json()["email"] == "new@example.ru"
    assert client.get(f"/invite/{token}").status_code == 404


def test_blocked_user_loses_session_and_cannot_login(monkeypatch):
    client, store, _ = build_app(monkeypatch)
    user = store.add_user("user@example.ru")
    login(client, "user@example.ru")
    assert client.get("/me").status_code == 200

    asyncio.run(store.set_active(user["id"], False))
    assert client.get("/me").status_code == 401
    assert login(client, "user@example.ru").status_code == 401


def test_login_throttle_blocks_after_email_limit(monkeypatch):
    client, store, _ = build_app(monkeypatch)
    store.add_user("user@example.ru")

    for _ in range(5):
        assert login(client, "user@example.ru", "wrong password").status_code == 401
    assert login(client, "user@example.ru", "wrong password").status_code == 429


def test_password_change_revokes_other_sessions(monkeypatch):
    client, store, app = build_app(monkeypatch)
    store.add_user("user@example.ru")
    login(client, "user@example.ru")

    other = TestClient(app)
    assert login(other, "user@example.ru").status_code == 303
    assert other.get("/me").status_code == 200

    response = client.post(
        "/password",
        data={
            "current_password": "correct horse battery",
            "new_password": "brand new password",
            "confirm_password": "brand new password",
            "csrf_token": csrf_token(client),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert other.get("/me").status_code == 401
    assert client.get("/me").status_code == 200


def test_login_page_escapes_email(monkeypatch):
    client, _, _ = build_app(monkeypatch)
    response = login(client, "<script>alert(1)</script>@example.ru", "wrong password")
    assert response.status_code == 401
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;" in response.text


def test_no_local_storage_in_web_assets():
    root = Path(__file__).resolve().parents[1] / "app" / "web"
    for path in root.rglob("*"):
        if path.suffix in {".js", ".html", ".css"}:
            assert "localStorage" not in path.read_text(encoding="utf-8"), path


def test_login_sets_csrf_cookie(monkeypatch):
    client, _, _ = build_app(monkeypatch)
    assert start(client)
