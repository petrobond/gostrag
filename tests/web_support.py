"""Shared helpers for web UI tests (in-memory store, fake RAG service)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.rag.generator import Answer, Citation
from app.rag.retriever import RetrievedChunk
from app.web.security import hash_password


class InMemoryWebStore:
    def __init__(self) -> None:
        self.users: dict[str, dict] = {}
        self.passwords: dict[str, str] = {}
        self.sessions: dict[str, dict] = {}
        self.invites: dict[str, dict] = {}
        self.attempts: dict[str, list[datetime]] = {}
        self.conversations: dict[str, dict] = {}
        self.messages: dict[str, dict] = {}

    def add_user(
        self,
        email: str,
        password: str = "correct horse battery",
        role: str = "user",
        is_active: bool = True,
    ) -> dict:
        user_id = str(uuid.uuid4())
        self.users[user_id] = {
            "id": user_id,
            "email": email.lower(),
            "role": role,
            "is_active": is_active,
            "must_change_password": False,
            "created_at": datetime.now(UTC),
            "last_login": None,
        }
        self.passwords[user_id] = hash_password(password)
        return self.users[user_id]

    async def create_user(
        self,
        email: str,
        role: str = "user",
        password_hash: str | None = None,
        is_active: bool = True,
    ) -> dict:
        user = self.add_user(email, role=role, is_active=is_active)
        if password_hash:
            self.passwords[user["id"]] = password_hash
        return {**user, "password_hash": self.passwords.get(user["id"])}

    async def get_user_by_email(self, email: str) -> dict | None:
        for user in self.users.values():
            if user["email"] == email.lower():
                return {**user, "password_hash": self.passwords.get(user["id"])}
        return None

    async def get_user(self, user_id: str) -> dict | None:
        user = self.users.get(str(user_id))
        if user is None:
            return None
        return {**user, "password_hash": self.passwords.get(user["id"])}

    async def list_users(self) -> list[dict]:
        return [dict(user) for user in self.users.values()]

    async def set_password(self, user_id: str, password_hash: str) -> None:
        self.passwords[str(user_id)] = password_hash
        if str(user_id) in self.users:
            self.users[str(user_id)]["must_change_password"] = False

    async def set_active(self, user_id: str, active: bool) -> None:
        if str(user_id) in self.users:
            self.users[str(user_id)]["is_active"] = active
        if not active:
            await self.revoke_user_sessions(user_id)

    async def touch_login(self, user_id: str) -> None:
        if str(user_id) in self.users:
            self.users[str(user_id)]["last_login"] = datetime.now(UTC)

    async def create_session(
        self,
        user_id: str,
        session_token_hash: str,
        expires_at: datetime,
        ip: str | None,
        user_agent: str | None,
    ) -> dict:
        session = {
            "session_id": str(uuid.uuid4()),
            "user_id": str(user_id),
            "expires_at": expires_at,
            "last_seen_at": datetime.now(UTC),
            "revoked_at": None,
            "ip": ip,
            "user_agent": user_agent,
        }
        self.sessions[session_token_hash] = session
        return session

    async def get_session(self, session_token_hash: str) -> dict | None:
        session = self.sessions.get(session_token_hash)
        if session is None:
            return None
        user = self.users.get(session["user_id"])
        if user is None:
            return None
        return {
            **session,
            "email": user["email"],
            "role": user["role"],
            "is_active": user["is_active"],
            "must_change_password": user["must_change_password"],
        }

    async def touch_session(self, session_id: str) -> None:
        for session in self.sessions.values():
            if session["session_id"] == str(session_id):
                session["last_seen_at"] = datetime.now(UTC)

    async def revoke_session(self, session_id: str) -> None:
        for session in self.sessions.values():
            if session["session_id"] == str(session_id):
                session["revoked_at"] = datetime.now(UTC)

    async def revoke_user_sessions(
        self, user_id: str, keep_session_id: str | None = None
    ) -> None:
        for session in self.sessions.values():
            if session["user_id"] != str(user_id):
                continue
            if keep_session_id and session["session_id"] == str(keep_session_id):
                continue
            session["revoked_at"] = datetime.now(UTC)

    # invites
    async def create_invite(
        self,
        email: str,
        role: str,
        purpose: str,
        invite_token_hash: str,
        created_by: str | None,
        expires_at: datetime,
    ) -> dict:
        invite = {
            "id": str(uuid.uuid4()),
            "email": email,
            "role": role,
            "purpose": purpose,
            "expires_at": expires_at,
            "used_at": None,
            "created_at": datetime.now(UTC),
        }
        self.invites[invite_token_hash] = invite
        return dict(invite)

    async def get_invite(self, invite_token_hash: str) -> dict | None:
        return self.invites.get(invite_token_hash)

    async def mark_invite_used(self, invite_id: str) -> None:
        for invite in self.invites.values():
            if invite["id"] == str(invite_id):
                invite["used_at"] = datetime.now(UTC)

    # login attempts
    async def count_login_attempts(self, key: str, window_sec: int) -> int:
        now = datetime.now(UTC)
        recent = [
            stamp
            for stamp in self.attempts.get(key, [])
            if (now - stamp).total_seconds() <= window_sec
        ]
        self.attempts[key] = recent
        return len(recent)

    async def record_login_attempt(self, key: str) -> None:
        self.attempts.setdefault(key, []).append(datetime.now(UTC))

    async def clear_login_attempts(self, key: str) -> None:
        self.attempts.pop(key, None)

    # conversations
    async def create_conversation(self, user_id: str, title: str) -> dict:
        conversation = {
            "id": str(uuid.uuid4()),
            "user_id": str(user_id),
            "title": title[:200],
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        self.conversations[conversation["id"]] = conversation
        return dict(conversation)

    async def list_conversations(self, user_id: str, limit: int = 50) -> list[dict]:
        items = [
            conversation
            for conversation in self.conversations.values()
            if conversation["user_id"] == str(user_id)
        ]
        items.sort(key=lambda item: item["updated_at"], reverse=True)
        return [
            {
                **conversation,
                "messages": sum(
                    1
                    for message in self.messages.values()
                    if message["conversation_id"] == conversation["id"]
                ),
            }
            for conversation in items[:limit]
        ]

    async def get_conversation(self, conversation_id: str, user_id: str) -> dict | None:
        conversation = self.conversations.get(str(conversation_id))
        if conversation is None or conversation["user_id"] != str(user_id):
            return None
        return dict(conversation)

    async def delete_conversation(self, conversation_id: str, user_id: str) -> bool:
        conversation = await self.get_conversation(conversation_id, user_id)
        if conversation is None:
            return False
        self.conversations.pop(conversation["id"], None)
        for message_id, message in list(self.messages.items()):
            if message["conversation_id"] == conversation["id"]:
                self.messages.pop(message_id, None)
        return True

    async def touch_conversation(self, conversation_id: str, title: str | None = None) -> None:
        conversation = self.conversations.get(str(conversation_id))
        if conversation is None:
            return
        conversation["updated_at"] = datetime.now(UTC)
        if title:
            conversation["title"] = title[:200]

    # messages
    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        citations_json: list[dict] | None = None,
        refused: bool = False,
        latency_ms: int | None = None,
        model: str | None = None,
    ) -> dict:
        message = {
            "id": str(uuid.uuid4()),
            "conversation_id": str(conversation_id),
            "role": role,
            "content": content,
            "citations_json": citations_json or [],
            "refused": refused,
            "latency_ms": latency_ms,
            "model": model,
            "created_at": datetime.now(UTC),
        }
        self.messages[message["id"]] = message
        return dict(message)

    async def list_messages(self, conversation_id: str) -> list[dict]:
        items = [
            message
            for message in self.messages.values()
            if message["conversation_id"] == str(conversation_id)
        ]
        items.sort(key=lambda item: item["created_at"])
        return [dict(message) for message in items]

    async def web_stats(self, days: int = 30) -> dict:
        assistants = [
            message for message in self.messages.values() if message["role"] == "assistant"
        ]
        latencies = sorted(
            message["latency_ms"]
            for message in assistants
            if message["latency_ms"] is not None
        )

        def percentile(value: float) -> float:
            if not latencies:
                return 0.0
            index = min(len(latencies) - 1, int(round((len(latencies) - 1) * value)))
            return float(latencies[index])

        active_users = {
            self.conversations[message["conversation_id"]]["user_id"]
            for message in assistants
            if message["conversation_id"] in self.conversations
        }
        return {
            "questions": len(assistants),
            "refusals": sum(1 for message in assistants if message["refused"]),
            "p50": percentile(0.5),
            "p95": percentile(0.95),
            "days": days,
            "active_users": len(active_users),
            "users_total": len(self.users),
            "users_active": sum(1 for user in self.users.values() if user["last_login"]),
            "conversations": len(self.conversations),
        }


class FakeAskService:
    def __init__(
        self,
        *,
        refused: bool = False,
        fail: bool = False,
        answer_text: str = "Ответ по стандарту.",
    ) -> None:
        self.refused = refused
        self.fail = fail
        self.answer_text = answer_text
        self.calls: list[tuple[str, int | None]] = []

    async def ask(self, question: str, top_k: int | None = None):
        self.calls.append((question, top_k))
        if self.fail:
            raise RuntimeError("llm down")
        citation = Citation(
            gost="ГОСТ Р 71476—2024",
            clause="3.1",
            page=5,
            quote="Определение из стандарта",
            file="gost-r-71476-2024.pdf",
            valid=True,
            page_valid=True,
            quote_valid=True,
        )
        answer = Answer(
            answer="В корпусе нет ответа на этот вопрос." if self.refused else self.answer_text,
            citations=[] if self.refused else [citation],
            confidence=0.9,
            refused=self.refused,
            missing=["ГОСТ"] if self.refused else [],
            model="fake",
            provider="fake",
        )
        chunk = RetrievedChunk(
            chunk_id="doc#3.1",
            text="Определение из стандарта",
            gost_number="ГОСТ Р 71476—2024",
            clause="3.1",
            section="3",
            section_title="Термины",
            page=5,
            score=1.0,
            doc_id="doc",
            file="gost-r-71476-2024.pdf",
        )
        return SimpleNamespace(answer=answer, chunks=[chunk], latency_ms=42)


class FakeS3:
    def url_for(self, filename: str, page: int, expires: int = 604800) -> str:
        if not filename:
            return ""
        return f"https://s3.example/{filename}#page={page}"


def csrf_token(client: TestClient) -> str:
    return (
        client.cookies.get("gostrag_csrf")
        or client.cookies.get("__Host-gostrag_csrf")
        or ""
    )


def start(client: TestClient, path: str = "/login") -> str:
    response = client.get(path)
    assert response.status_code == 200, response.text
    return csrf_token(client)


def login(
    client: TestClient,
    email: str,
    password: str = "correct horse battery",
    *,
    follow_redirects: bool = False,
):
    token = start(client)
    return client.post(
        "/login",
        data={
            "email": email,
            "password": password,
            "csrf_token": token,
            "next": "/chat",
        },
        follow_redirects=follow_redirects,
    )


def build_app(monkeypatch, *, secure: bool = False, service=None, s3=None):
    monkeypatch.setenv("WEB_ENABLED", "true")
    monkeypatch.setenv("WEB_COOKIE_SECURE", "true" if secure else "false")
    get_settings.cache_clear()
    cfg = get_settings()
    app = create_app(cfg)
    store = InMemoryWebStore()
    app.state.web_store = store
    app.state.web_ready = True
    app.state.service = service if service is not None else FakeAskService()
    app.state.s3 = s3 if s3 is not None else FakeS3()
    base_url = "https://testserver" if secure else "http://testserver"
    return TestClient(app, base_url=base_url), store, app
