import json
import re

from fastapi.testclient import TestClient
from web_support import build_app, csrf_token, login


def _admin_client(monkeypatch):
    client, store, app = build_app(monkeypatch)
    store.add_user("admin@example.ru", role="admin")
    login(client, "admin@example.ru")
    return client, store, app


def _token_from(text: str) -> str:
    match = re.search(r"/invite/([A-Za-z0-9_\-]+)", text)
    assert match, "invite link not found"
    return match.group(1)


def test_regular_user_cannot_open_admin(monkeypatch):
    client, store, _ = build_app(monkeypatch)
    store.add_user("user@example.ru")
    login(client, "user@example.ru")

    assert client.get("/admin").status_code == 403
    assert client.get("/admin/users").status_code == 403
    assert client.get("/api/web/admin/stats").status_code == 403


def test_admin_stats_api_and_page(monkeypatch):
    client, store, _ = _admin_client(monkeypatch)
    token = csrf_token(client)
    client.post(
        "/api/web/ask",
        json={"question": "Что такое качество данных?"},
        headers={"X-CSRF-Token": token},
    )

    stats = client.get("/api/web/admin/stats").json()
    assert stats["questions"] == 1
    assert {"corpus_version", "collection", "index_ready", "web_ready", "telegram"} <= set(stats)
    assert client.get("/admin").status_code == 200


def test_admin_invite_flow_creates_regular_user(monkeypatch):
    client, _, app = _admin_client(monkeypatch)
    page = client.post(
        "/admin/users/invite",
        data={"email": "new@example.ru", "csrf_token": csrf_token(client)},
    )
    assert page.status_code == 200
    assert "Одноразовая ссылка-приглашение" in page.text
    token = _token_from(page.text)

    fresh = TestClient(app)
    assert fresh.get(f"/invite/{token}").status_code == 200
    accept = fresh.post(
        f"/invite/{token}",
        data={
            "password": "new user password",
            "confirm_password": "new user password",
            "csrf_token": csrf_token(fresh),
        },
        follow_redirects=False,
    )
    assert accept.status_code == 303

    me = fresh.get("/me").json()
    assert me["email"] == "new@example.ru"
    assert me["role"] == "user"


def test_admin_blocks_and_unblocks_user(monkeypatch):
    admin_client, store, app = _admin_client(monkeypatch)
    user = store.add_user("user@example.ru")

    user_client = TestClient(app)
    assert login(user_client, "user@example.ru").status_code == 303
    assert user_client.get("/me").status_code == 200

    blocked = admin_client.post(
        f"/admin/users/{user['id']}/block",
        data={"csrf_token": csrf_token(admin_client)},
        follow_redirects=False,
    )
    assert blocked.status_code == 303
    assert user_client.get("/me").status_code == 401

    unblocked = admin_client.post(
        f"/admin/users/{user['id']}/unblock",
        data={"csrf_token": csrf_token(admin_client)},
        follow_redirects=False,
    )
    assert unblocked.status_code == 303
    assert login(user_client, "user@example.ru").status_code == 303


def test_admin_cannot_block_self(monkeypatch):
    client, store, _ = build_app(monkeypatch)
    admin = store.add_user("admin@example.ru", role="admin")
    login(client, "admin@example.ru")

    response = client.post(
        f"/admin/users/{admin['id']}/block",
        data={"csrf_token": csrf_token(client)},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert client.get("/me").status_code == 200


def test_password_reset_link(monkeypatch):
    admin_client, store, app = _admin_client(monkeypatch)
    user = store.add_user("user@example.ru")

    page = admin_client.post(
        f"/admin/users/{user['id']}/reset",
        data={"csrf_token": csrf_token(admin_client)},
    )
    assert page.status_code == 200
    token = _token_from(page.text)

    fresh = TestClient(app)
    assert fresh.get(f"/invite/{token}").status_code == 200
    accept = fresh.post(
        f"/invite/{token}",
        data={
            "password": "reset password 1",
            "confirm_password": "reset password 1",
            "csrf_token": csrf_token(fresh),
        },
        follow_redirects=False,
    )
    assert accept.status_code == 303
    assert fresh.get("/me").json()["email"] == "user@example.ru"

    other = TestClient(app)
    assert login(other, "user@example.ru").status_code == 401
    assert login(other, "user@example.ru", "reset password 1").status_code == 303


def test_documents_page_lists_corpus(monkeypatch, tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "documents.json").write_text(
        json.dumps(
            [
                {
                    "doc_id": "doc",
                    "gost_number": "ГОСТ Р 71476—2024",
                    "title": "Качество данных",
                    "pages": 20,
                    "chunks": 100,
                    "filename": "gost.pdf",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DATA_CORPUS_DIR", str(corpus))

    client, store, _ = _admin_client(monkeypatch)
    page = client.get("/admin/documents")
    assert page.status_code == 200
    assert "ГОСТ Р 71476—2024" in page.text
    assert "gost.pdf#page=1" in page.text


def test_audit_listing_view_and_path_traversal(monkeypatch, tmp_path):
    reports = tmp_path / "reports"
    (reports / "3.3.0" / "1").mkdir(parents=True)
    (reports / "3.3.0" / "1" / "audit.md").write_text(
        "# Аудит\n<script>alert(1)</script>\n", encoding="utf-8"
    )
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
    monkeypatch.setenv("REPORTS_DIR", str(reports))

    client, _, _ = _admin_client(monkeypatch)
    page = client.get("/admin/audit")
    assert page.status_code == 200
    assert "3.3.0/1/audit.md" in page.text

    view = client.get("/admin/audit/view?root=reports&path=3.3.0/1/audit.md")
    assert view.status_code == 200
    assert "<script>alert(1)</script>" not in view.text
    assert "&lt;script&gt;" in view.text

    traversal = client.get("/admin/audit/view?root=reports&path=../secret.txt")
    assert traversal.status_code == 404
