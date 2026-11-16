import os
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest
import pytest_asyncio

from app.web.migrations import apply_migrations
from app.web.security import token_hash
from app.web.store import WebStore

DSN = os.getenv("TEST_POSTGRES_DSN", "")
pytestmark = pytest.mark.skipif(not DSN, reason="TEST_POSTGRES_DSN is not set")

TABLES = (
    "web_messages, web_conversations, web_sessions, "
    "web_invites, web_login_attempts, web_users"
)


@pytest_asyncio.fixture
async def store():
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=2, timeout=5)
    await apply_migrations(pool)
    await pool.execute(f"TRUNCATE {TABLES} CASCADE")
    try:
        yield WebStore(pool)
    finally:
        await pool.close()


async def test_migrations_are_idempotent(store):
    assert await apply_migrations(store.pool) == []


async def test_user_session_and_invite_roundtrip(store):
    user = await store.create_user("user@example.ru", role="user", password_hash="hash")
    assert user["email"] == "user@example.ru"

    session = await store.create_session(
        user["id"],
        token_hash("token"),
        datetime.now(UTC) + timedelta(days=1),
        "127.0.0.1",
        "pytest",
    )
    found = await store.get_session(token_hash("token"))
    assert found["email"] == "user@example.ru"
    assert str(found["session_id"]) == str(session["id"])

    await store.revoke_session(session["id"])
    assert (await store.get_session(token_hash("token")))["revoked_at"] is not None

    invite = await store.create_invite(
        "new@example.ru",
        "user",
        "invite",
        token_hash("invite"),
        user["id"],
        datetime.now(UTC) + timedelta(days=1),
    )
    assert invite["purpose"] == "invite"
    stored_invite = await store.get_invite(token_hash("invite"))
    assert stored_invite["email"] == "new@example.ru"


async def test_session_stores_only_hash(store):
    user = await store.create_user("hash@example.ru")
    raw = "raw-token-value"
    await store.create_session(
        user["id"], token_hash(raw), datetime.now(UTC) + timedelta(days=1), None, None
    )
    stored = await store.pool.fetchval("SELECT token_hash FROM web_sessions")
    assert stored == token_hash(raw)
    assert stored != raw


async def test_conversation_ownership_and_stats(store):
    alice = await store.create_user("alice@example.ru")
    bob = await store.create_user("bob@example.ru")

    conversation = await store.create_conversation(alice["id"], "Вопрос")
    assert await store.get_conversation(conversation["id"], bob["id"]) is None
    assert await store.get_conversation(conversation["id"], alice["id"]) is not None

    await store.add_message(conversation["id"], "user", "Что такое ИИ?")
    await store.add_message(
        conversation["id"],
        "assistant",
        "Ответ",
        citations_json=[{"gost": "ГОСТ Р 71476—2024", "page": 5}],
        refused=False,
        latency_ms=120,
        model="fake",
    )
    messages = await store.list_messages(conversation["id"])
    assert [message["role"] for message in messages] == ["user", "assistant"]

    stats = await store.web_stats(days=30)
    assert stats["questions"] == 1
    assert stats["refusals"] == 0
    assert stats["p50"] == 120.0
    assert stats["users_total"] == 2
    assert stats["conversations"] == 1

    assert await store.delete_conversation(conversation["id"], bob["id"]) is False
    assert await store.delete_conversation(conversation["id"], alice["id"]) is True
    assert await store.list_messages(conversation["id"]) == []


async def test_login_attempts_counter(store):
    await store.record_login_attempt("ip:127.0.0.1")
    await store.record_login_attempt("ip:127.0.0.1")
    assert await store.count_login_attempts("ip:127.0.0.1", 900) == 2
    await store.clear_login_attempts("ip:127.0.0.1")
    assert await store.count_login_attempts("ip:127.0.0.1", 900) == 0
