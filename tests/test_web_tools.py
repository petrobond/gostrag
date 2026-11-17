from urllib.parse import quote

from web_support import build_app, csrf_token, login


def _user_client(monkeypatch, role="user"):
    client, store, _ = build_app(monkeypatch)
    store.add_user("user@example.ru", role=role)
    login(client, "user@example.ru")
    return client


def test_guest_is_redirected_to_login(monkeypatch):
    client, _, _ = build_app(monkeypatch)
    response = client.get("/tools/gosts", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_standards_page_lists_corpus(monkeypatch):
    client = _user_client(monkeypatch)
    page = client.get("/tools/gosts")
    assert page.status_code == 200
    assert "Стандарты" in page.text
    assert "ГОСТ Р 71476—2024" in page.text


def test_standard_page_has_outline_terms_and_links(monkeypatch):
    client = _user_client(monkeypatch)
    gost = quote("ГОСТ Р 71476—2024", safe="")
    page = client.get(f"/tools/gosts/{gost}")
    assert page.status_code == 200
    assert "Разделы" in page.text
    assert "Термины (105)" in page.text
    assert "Связи" in page.text
    terms = client.get(f"/tools/gosts/{gost}?tab=terms")
    assert terms.status_code == 200
    assert "3.1.1" in terms.text
    links = client.get(f"/tools/gosts/{gost}?tab=links")
    assert links.status_code == 200
    assert "Исходящие" in links.text


def test_terms_search(monkeypatch):
    client = _user_client(monkeypatch)
    page = client.get("/tools/terms?q=агент")
    assert page.status_code == 200
    assert "агент" in page.text.lower()
    assert "ГОСТ Р 71476—2024" in page.text


def test_chat_has_command_palette(monkeypatch):
    client = _user_client(monkeypatch)
    page = client.get("/chat")
    assert page.status_code == 200
    assert "data-command-palette" in page.text
    assert "/tools/gosts" in page.text
    assert "/help" in page.text


def test_help_contains_public_commands_only_for_user(monkeypatch):

    client = _user_client(monkeypatch)
    page = client.get("/help")
    assert page.status_code == 200
    assert "/gosts" in page.text
    assert "/kb" in page.text
    assert "/stats" not in page.text


def test_slash_commands_redirect_to_tools(monkeypatch):
    client = _user_client(monkeypatch)
    headers = {"X-CSRF-Token": csrf_token(client)}
    response = client.post(
        "/web/ask",
        data={"question": "/gosts", "csrf_token": csrf_token(client)},
        headers=headers,
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tools/gosts"

    response = client.post(
        "/web/ask",
        data={"question": "/term агент", "csrf_token": csrf_token(client)},
        headers=headers,
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].startswith("/tools/terms?q=")

    response = client.post(
        "/web/ask",
        data={"question": "/ask Что такое ИИ?", "csrf_token": csrf_token(client)},
        headers=headers,
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].startswith("/chat/")


def test_admin_commands_are_forbidden_for_user(monkeypatch):
    client = _user_client(monkeypatch)
    response = client.post(
        "/web/ask",
        data={"question": "/stats", "csrf_token": csrf_token(client)},
        headers={"X-CSRF-Token": csrf_token(client)},
        follow_redirects=False,
    )
    assert response.status_code == 403


def test_admin_help_and_audit_status(monkeypatch):
    client = _user_client(monkeypatch, role="admin")
    page = client.get("/help")
    assert page.status_code == 200
    assert "/stats" in page.text
    assert "/audit_status" in page.text
    audit = client.get("/admin/audit")
    assert audit.status_code == 200
    assert "Статус аудита" in audit.text
