import asyncio

from web_support import FakeAskService, build_app, csrf_token, login


def _auth_headers(client):
    return {"X-CSRF-Token": csrf_token(client)}


def test_guest_cannot_use_web_api(monkeypatch):
    client, _, _ = build_app(monkeypatch)
    assert client.get("/api/web/conversations").status_code == 401
    assert client.post("/api/web/ask", json={"question": "Что такое ИИ?"}).status_code == 401
    response = client.get("/chat", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_api_ask_creates_conversation_and_citation(monkeypatch):
    client, store, app = build_app(monkeypatch)
    store.add_user("user@example.ru")
    login(client, "user@example.ru")

    response = client.post(
        "/api/web/ask",
        json={"question": "Что такое качество данных?", "top_k": 3},
        headers=_auth_headers(client),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["conversation_id"]
    assert payload["message_id"]
    assert payload["refused"] is False
    assert payload["citations"][0]["gost"] == "ГОСТ Р 71476—2024"
    assert payload["citations"][0]["pdf_url"].endswith("#page=5")
    assert app.state.service.calls == [("Что такое качество данных?", 3)]

    conversation = client.get(f"/api/web/conversations/{payload['conversation_id']}")
    assert conversation.status_code == 200
    assert [message["role"] for message in conversation.json()["messages"]] == [
        "user",
        "assistant",
    ]

    listing = client.get("/api/web/conversations").json()
    assert listing["conversations"][0]["messages"] == 2

    stored = next(
        message for message in store.messages.values() if message["role"] == "assistant"
    )
    assert "pdf_url" not in stored["citations_json"][0]


def test_api_ask_requires_csrf(monkeypatch):
    client, store, _ = build_app(monkeypatch)
    store.add_user("user@example.ru")
    login(client, "user@example.ru")

    response = client.post("/api/web/ask", json={"question": "Что такое ИИ?"})
    assert response.status_code == 403


def test_api_ask_validates_question(monkeypatch):
    client, store, _ = build_app(monkeypatch)
    store.add_user("user@example.ru")
    login(client, "user@example.ru")

    response = client.post(
        "/api/web/ask", json={"question": "a"}, headers=_auth_headers(client)
    )
    assert response.status_code == 422


def test_conversation_ownership_is_enforced(monkeypatch):
    client, store, _ = build_app(monkeypatch)
    store.add_user("alice@example.ru")
    store.add_user("bob@example.ru")
    login(client, "alice@example.ru")

    created = client.post(
        "/api/web/conversations",
        json={"title": "Alice"},
        headers=_auth_headers(client),
    ).json()

    client.post(
        "/logout", data={"csrf_token": csrf_token(client)}, follow_redirects=False
    )
    login(client, "bob@example.ru")

    assert client.get(f"/api/web/conversations/{created['id']}").status_code == 404
    assert client.get(f"/chat/{created['id']}").status_code == 404
    ask = client.post(
        "/api/web/ask",
        json={"question": "Вопрос по ГОСТ", "conversation_id": created["id"]},
        headers=_auth_headers(client),
    )
    assert ask.status_code == 404


def test_delete_conversation(monkeypatch):
    client, store, _ = build_app(monkeypatch)
    store.add_user("user@example.ru")
    login(client, "user@example.ru")

    created = client.post(
        "/api/web/conversations",
        json={"title": "Удалить"},
        headers=_auth_headers(client),
    ).json()
    response = client.delete(
        f"/api/web/conversations/{created['id']}", headers=_auth_headers(client)
    )
    assert response.status_code == 204
    assert client.get(f"/api/web/conversations/{created['id']}").status_code == 404

    created = client.post(
        "/api/web/conversations",
        json={"title": "Удалить"},
        headers=_auth_headers(client),
    ).json()
    page = client.post(
        f"/web/conversations/{created['id']}/delete",
        data={"csrf_token": csrf_token(client)},
        follow_redirects=False,
    )
    assert page.status_code == 303
    assert page.headers["location"] == "/chat"


def test_ask_failure_keeps_process_alive(monkeypatch):
    service = FakeAskService(fail=True)
    client, store, _ = build_app(monkeypatch, service=service)
    store.add_user("user@example.ru")
    login(client, "user@example.ru")

    response = client.post(
        "/api/web/ask",
        json={"question": "Что такое ИИ?"},
        headers=_auth_headers(client),
    )
    assert response.status_code == 502
    assert client.get("/me").status_code == 200


def test_refusal_is_stored_and_rendered(monkeypatch):
    service = FakeAskService(refused=True)
    client, store, _ = build_app(monkeypatch, service=service)
    store.add_user("user@example.ru")
    login(client, "user@example.ru")

    payload = client.post(
        "/api/web/ask",
        json={"question": "Вопрос вне корпуса"},
        headers=_auth_headers(client),
    ).json()
    assert payload["refused"] is True
    assert "нет ответа" in payload["answer"]

    page = client.get(f"/chat/{payload['conversation_id']}")
    assert page.status_code == 200
    assert "нет ответа" in page.text


def test_htmx_ask_returns_thread_and_conversation_list(monkeypatch):
    client, store, _ = build_app(monkeypatch)
    store.add_user("user@example.ru")
    login(client, "user@example.ru")
    assert client.get("/chat").status_code == 200

    token = csrf_token(client)
    response = client.post(
        "/web/ask",
        data={"question": "Что такое качество данных?", "csrf_token": token},
        headers={"HX-Request": "true", "X-CSRF-Token": token},
    )
    assert response.status_code == 200
    assert 'hx-swap-oob="true"' in response.text
    assert "gost-r-71476-2024.pdf#page=5" in response.text
    assert "Что такое качество данных?" in response.text


def test_plain_form_ask_redirects_to_conversation(monkeypatch):
    client, store, _ = build_app(monkeypatch)
    store.add_user("user@example.ru")
    login(client, "user@example.ru")

    response = client.post(
        "/web/ask",
        data={
            "question": "Что такое качество данных?",
            "csrf_token": csrf_token(client),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/chat/")

    page = client.get(location)
    assert page.status_code == 200
    assert "ГОСТ Р 71476—2024" in page.text
    assert "#page=5" in page.text


def test_answer_is_escaped_on_history_page(monkeypatch):
    service = FakeAskService(answer_text='<script>alert("x")</script>')
    client, store, _ = build_app(monkeypatch, service=service)
    store.add_user("user@example.ru")
    login(client, "user@example.ru")

    payload = client.post(
        "/api/web/ask",
        json={"question": "Что такое ИИ?"},
        headers=_auth_headers(client),
    ).json()
    page = client.get(f"/chat/{payload['conversation_id']}")
    assert page.status_code == 200
    assert "<script>alert" not in page.text
    assert "&lt;script&gt;" in page.text


def test_new_conversation_button_creates_empty_dialog(monkeypatch):
    client, store, _ = build_app(monkeypatch)
    store.add_user("user@example.ru")
    login(client, "user@example.ru")

    response = client.post(
        "/web/conversations/new",
        data={"csrf_token": csrf_token(client)},
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/chat/")
    page = client.get(location)
    assert page.status_code == 200
    assert "Новый диалог" in page.text


def test_meta_citation_hides_clause_label(monkeypatch):
    client, store, _ = build_app(monkeypatch)
    user = store.add_user("user@example.ru")
    login(client, "user@example.ru")
    conversation = asyncio.run(store.create_conversation(user["id"], "Список"))
    asyncio.run(
        store.add_message(
            conversation["id"],
            "assistant",
            "В корпусе 1 стандарт.",
            citations_json=[
                {
                    "gost": "ГОСТ Р 1—2024",
                    "clause": "meta",
                    "page": 1,
                    "quote": "Первый стандарт",
                    "file": "one.pdf",
                }
            ],
        )
    )
    page = client.get(f"/chat/{conversation['id']}")
    assert page.status_code == 200
    assert "ГОСТ Р 1—2024, с. 1" in page.text
    assert "п. meta" not in page.text


def test_first_question_replaces_default_title(monkeypatch):

    client, store, _ = build_app(monkeypatch)
    store.add_user("user@example.ru")
    login(client, "user@example.ru")

    created = client.post(
        "/web/conversations/new",
        data={"csrf_token": csrf_token(client)},
        follow_redirects=False,
    )
    conversation_id = created.headers["location"].rsplit("/", 1)[-1]

    client.post(
        "/api/web/ask",
        json={
            "question": "Что такое качество данных?",
            "conversation_id": conversation_id,
        },
        headers=_auth_headers(client),
    )
    conversation = client.get(f"/api/web/conversations/{conversation_id}").json()
    assert conversation["title"] == "Что такое качество данных?"
