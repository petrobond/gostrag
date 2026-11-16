"""PostgreSQL access layer for the web UI (asyncpg, no ORM)."""

from __future__ import annotations

import ipaddress
import json
import uuid
from datetime import datetime
from typing import Any

import asyncpg


def parse_uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def _inet(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def _row(record: asyncpg.Record | None) -> dict[str, Any] | None:
    return dict(record) if record is not None else None


class WebStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    # --- users -----------------------------------------------------------
    async def create_user(
        self,
        email: str,
        role: str = "user",
        password_hash: str | None = None,
        is_active: bool = True,
    ) -> dict[str, Any]:
        row = await self.pool.fetchrow(
            "INSERT INTO web_users(email, role, password_hash, is_active) "
            "VALUES($1, $2, $3, $4) "
            "RETURNING id, email, role, is_active, must_change_password, "
            "created_at, last_login, password_hash",
            email,
            role,
            password_hash,
            is_active,
        )
        return dict(row)

    async def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        row = await self.pool.fetchrow(
            "SELECT id, email, role, is_active, must_change_password, password_hash, "
            "created_at, last_login FROM web_users WHERE email = $1",
            email,
        )
        return _row(row)

    async def get_user(self, user_id: uuid.UUID | str) -> dict[str, Any] | None:
        parsed = parse_uuid(user_id)
        if parsed is None:
            return None
        row = await self.pool.fetchrow(
            "SELECT id, email, role, is_active, must_change_password, password_hash, "
            "created_at, last_login FROM web_users WHERE id = $1",
            parsed,
        )
        return _row(row)

    async def list_users(self) -> list[dict[str, Any]]:
        rows = await self.pool.fetch(
            "SELECT id, email, role, is_active, must_change_password, created_at, last_login "
            "FROM web_users ORDER BY created_at"
        )
        return [dict(row) for row in rows]

    async def set_password(self, user_id: uuid.UUID | str, password_hash: str) -> None:
        parsed = parse_uuid(user_id)
        if parsed is None:
            return
        await self.pool.execute(
            "UPDATE web_users SET password_hash = $2, must_change_password = FALSE WHERE id = $1",
            parsed,
            password_hash,
        )

    async def set_active(self, user_id: uuid.UUID | str, active: bool) -> None:
        parsed = parse_uuid(user_id)
        if parsed is None:
            return
        await self.pool.execute(
            "UPDATE web_users SET is_active = $2 WHERE id = $1", parsed, active
        )
        if not active:
            await self.revoke_user_sessions(parsed)

    async def touch_login(self, user_id: uuid.UUID | str) -> None:
        parsed = parse_uuid(user_id)
        if parsed is None:
            return
        await self.pool.execute("UPDATE web_users SET last_login = now() WHERE id = $1", parsed)

    # --- sessions --------------------------------------------------------
    async def create_session(
        self,
        user_id: uuid.UUID | str,
        session_token_hash: str,
        expires_at: datetime,
        ip: str | None,
        user_agent: str | None,
    ) -> dict[str, Any]:
        row = await self.pool.fetchrow(
            "INSERT INTO web_sessions(user_id, token_hash, expires_at, ip, user_agent) "
            "VALUES($1, $2, $3, $4::inet, $5) "
            "RETURNING id, user_id, expires_at, created_at",
            uuid.UUID(str(user_id)),
            session_token_hash,
            expires_at,
            _inet(ip),
            (user_agent or "")[:512] or None,
        )
        return dict(row)

    async def get_session(self, session_token_hash: str) -> dict[str, Any] | None:
        row = await self.pool.fetchrow(
            "SELECT s.id AS session_id, s.user_id, s.expires_at, s.last_seen_at, s.revoked_at, "
            "u.email, u.role, u.is_active, u.must_change_password "
            "FROM web_sessions s JOIN web_users u ON u.id = s.user_id "
            "WHERE s.token_hash = $1",
            session_token_hash,
        )
        return _row(row)

    async def touch_session(self, session_id: uuid.UUID | str) -> None:
        parsed = parse_uuid(session_id)
        if parsed is None:
            return
        await self.pool.execute(
            "UPDATE web_sessions SET last_seen_at = now() "
            "WHERE id = $1 AND last_seen_at < now() - interval '5 minutes'",
            parsed,
        )

    async def revoke_session(self, session_id: uuid.UUID | str) -> None:
        parsed = parse_uuid(session_id)
        if parsed is None:
            return
        await self.pool.execute(
            "UPDATE web_sessions SET revoked_at = now() WHERE id = $1 AND revoked_at IS NULL",
            parsed,
        )

    async def revoke_user_sessions(
        self,
        user_id: uuid.UUID | str,
        keep_session_id: uuid.UUID | str | None = None,
    ) -> None:
        parsed_user = parse_uuid(user_id)
        if parsed_user is None:
            return
        keep = parse_uuid(keep_session_id) if keep_session_id else None
        await self.pool.execute(
            "UPDATE web_sessions SET revoked_at = now() "
            "WHERE user_id = $1 AND revoked_at IS NULL AND ($2::uuid IS NULL OR id <> $2::uuid)",
            parsed_user,
            keep,
        )

    # --- invites ---------------------------------------------------------
    async def create_invite(
        self,
        email: str,
        role: str,
        purpose: str,
        invite_token_hash: str,
        created_by: uuid.UUID | str | None,
        expires_at: datetime,
    ) -> dict[str, Any]:
        row = await self.pool.fetchrow(
            "INSERT INTO web_invites(email, role, purpose, token_hash, created_by, expires_at) "
            "VALUES($1, $2, $3, $4, $5, $6) "
            "RETURNING id, email, role, purpose, expires_at, created_at",
            email,
            role,
            purpose,
            invite_token_hash,
            parse_uuid(created_by) if created_by else None,
            expires_at,
        )
        return dict(row)

    async def get_invite(self, invite_token_hash: str) -> dict[str, Any] | None:
        row = await self.pool.fetchrow(
            "SELECT id, email, role, purpose, expires_at, used_at, created_at "
            "FROM web_invites WHERE token_hash = $1",
            invite_token_hash,
        )
        return _row(row)

    async def mark_invite_used(self, invite_id: uuid.UUID | str) -> None:
        parsed = parse_uuid(invite_id)
        if parsed is None:
            return
        await self.pool.execute(
            "UPDATE web_invites SET used_at = now() WHERE id = $1 AND used_at IS NULL", parsed
        )

    # --- login attempts --------------------------------------------------
    async def count_login_attempts(self, key: str, window_sec: int) -> int:
        value = await self.pool.fetchval(
            "SELECT count(*) FROM web_login_attempts "
            "WHERE key = $1 AND created_at >= now() - ($2::int * interval '1 second')",
            key,
            window_sec,
        )
        return int(value or 0)

    async def record_login_attempt(self, key: str) -> None:
        await self.pool.execute("INSERT INTO web_login_attempts(key) VALUES($1)", key)
        await self.pool.execute(
            "DELETE FROM web_login_attempts WHERE created_at < now() - interval '1 day'"
        )

    async def clear_login_attempts(self, key: str) -> None:
        await self.pool.execute("DELETE FROM web_login_attempts WHERE key = $1", key)

    # --- conversations ---------------------------------------------------
    async def create_conversation(
        self, user_id: uuid.UUID | str, title: str
    ) -> dict[str, Any]:
        row = await self.pool.fetchrow(
            "INSERT INTO web_conversations(user_id, title) VALUES($1, $2) "
            "RETURNING id, title, created_at, updated_at",
            uuid.UUID(str(user_id)),
            title[:200],
        )
        return dict(row)

    async def list_conversations(
        self, user_id: uuid.UUID | str, limit: int = 50
    ) -> list[dict[str, Any]]:
        rows = await self.pool.fetch(
            "SELECT c.id, c.title, c.created_at, c.updated_at, "
            "(SELECT count(*) FROM web_messages m WHERE m.conversation_id = c.id) AS messages "
            "FROM web_conversations c WHERE c.user_id = $1 "
            "ORDER BY c.updated_at DESC LIMIT $2",
            uuid.UUID(str(user_id)),
            limit,
        )
        return [dict(row) for row in rows]

    async def get_conversation(
        self, conversation_id: uuid.UUID | str, user_id: uuid.UUID | str
    ) -> dict[str, Any] | None:
        parsed_conversation = parse_uuid(conversation_id)
        parsed_user = parse_uuid(user_id)
        if parsed_conversation is None or parsed_user is None:
            return None
        row = await self.pool.fetchrow(
            "SELECT id, user_id, title, created_at, updated_at FROM web_conversations "
            "WHERE id = $1 AND user_id = $2",
            parsed_conversation,
            parsed_user,
        )
        return _row(row)

    async def delete_conversation(
        self, conversation_id: uuid.UUID | str, user_id: uuid.UUID | str
    ) -> bool:
        parsed_conversation = parse_uuid(conversation_id)
        parsed_user = parse_uuid(user_id)
        if parsed_conversation is None or parsed_user is None:
            return False
        deleted = await self.pool.fetchval(
            "DELETE FROM web_conversations WHERE id = $1 AND user_id = $2 RETURNING id",
            parsed_conversation,
            parsed_user,
        )
        return deleted is not None

    async def touch_conversation(
        self, conversation_id: uuid.UUID | str, title: str | None = None
    ) -> None:
        parsed = parse_uuid(conversation_id)
        if parsed is None:
            return
        await self.pool.execute(
            "UPDATE web_conversations SET updated_at = now(), title = COALESCE($2, title) "
            "WHERE id = $1",
            parsed,
            title[:200] if title else None,
        )

    # --- messages --------------------------------------------------------
    async def add_message(
        self,
        conversation_id: uuid.UUID | str,
        role: str,
        content: str,
        citations_json: list[dict[str, Any]] | None = None,
        refused: bool = False,
        latency_ms: int | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        row = await self.pool.fetchrow(
            "INSERT INTO web_messages(conversation_id, role, content, citations_json, "
            "refused, latency_ms, model) VALUES($1, $2, $3, $4::jsonb, $5, $6, $7) "
            "RETURNING id, role, content, citations_json, refused, latency_ms, model, created_at",
            uuid.UUID(str(conversation_id)),
            role,
            content,
            json.dumps(citations_json or [], ensure_ascii=False),
            refused,
            latency_ms,
            model,
        )
        return dict(row)

    async def list_messages(self, conversation_id: uuid.UUID | str) -> list[dict[str, Any]]:
        parsed = parse_uuid(conversation_id)
        if parsed is None:
            return []
        rows = await self.pool.fetch(
            "SELECT id, role, content, citations_json, refused, latency_ms, model, created_at "
            "FROM web_messages WHERE conversation_id = $1 ORDER BY created_at, id",
            parsed,
        )
        return [dict(row) for row in rows]

    # --- stats -----------------------------------------------------------
    async def web_stats(self, days: int = 30) -> dict[str, Any]:
        row = await self.pool.fetchrow(
            "SELECT count(*) AS questions, "
            "count(*) FILTER (WHERE m.refused) AS refusals, "
            "percentile_cont(0.5) WITHIN GROUP (ORDER BY m.latency_ms) AS p50, "
            "percentile_cont(0.95) WITHIN GROUP (ORDER BY m.latency_ms) AS p95 "
            "FROM web_messages m JOIN web_conversations c ON c.id = m.conversation_id "
            "WHERE m.role = 'assistant' "
            "AND m.created_at >= now() - ($1::int * interval '1 day')",
            days,
        )
        active = await self.pool.fetchval(
            "SELECT count(DISTINCT c.user_id) FROM web_messages m "
            "JOIN web_conversations c ON c.id = m.conversation_id "
            "WHERE m.created_at >= now() - ($1::int * interval '1 day')",
            days,
        )
        users = await self.pool.fetchrow(
            "SELECT count(*) AS total, "
            "count(*) FILTER (WHERE last_login >= now() - interval '7 days') AS active "
            "FROM web_users"
        )
        conversations = await self.pool.fetchval("SELECT count(*) FROM web_conversations")
        result = dict(row) if row else {}
        result.update(
            {
                "days": days,
                "active_users": int(active or 0),
                "users_total": int((users or {}).get("total") or 0),
                "users_active": int((users or {}).get("active") or 0),
                "conversations": int(conversations or 0),
            }
        )
        result["p50"] = round(float(result.get("p50") or 0), 1)
        result["p95"] = round(float(result.get("p95") or 0), 1)
        return result
