"""Idempotent SQL migrations for the web UI (applied on startup under a lock)."""

from __future__ import annotations

import asyncpg

LOCK_KEY = 7_203_311_001

MIGRATIONS: list[tuple[str, str]] = [
    (
        "0001_web_auth",
        """
        CREATE TABLE IF NOT EXISTS web_users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT,
            role TEXT NOT NULL DEFAULT 'user',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            must_change_password BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_login TIMESTAMPTZ,
            CONSTRAINT web_users_email_lower CHECK (email = lower(email)),
            CONSTRAINT web_users_role CHECK (role IN ('user', 'admin'))
        );

        CREATE TABLE IF NOT EXISTS web_sessions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES web_users(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TIMESTAMPTZ NOT NULL,
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            revoked_at TIMESTAMPTZ,
            ip INET,
            user_agent TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_web_sessions_user ON web_sessions(user_id);

        CREATE TABLE IF NOT EXISTS web_invites (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            purpose TEXT NOT NULL DEFAULT 'invite',
            token_hash TEXT NOT NULL UNIQUE,
            created_by UUID REFERENCES web_users(id) ON DELETE SET NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            used_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT web_invites_email_lower CHECK (email = lower(email)),
            CONSTRAINT web_invites_role CHECK (role IN ('user', 'admin')),
            CONSTRAINT web_invites_purpose CHECK (purpose IN ('invite', 'reset'))
        );
        CREATE INDEX IF NOT EXISTS idx_web_invites_email ON web_invites(email);

        CREATE TABLE IF NOT EXISTS web_login_attempts (
            key TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_web_login_attempts_key
            ON web_login_attempts(key, created_at);
        """,
    ),
    (
        "0002_web_chat",
        """
        CREATE TABLE IF NOT EXISTS web_conversations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES web_users(id) ON DELETE CASCADE,
            title TEXT NOT NULL DEFAULT 'Новый диалог',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_web_conversations_user
            ON web_conversations(user_id, updated_at DESC);

        CREATE TABLE IF NOT EXISTS web_messages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id UUID NOT NULL REFERENCES web_conversations(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            citations_json JSONB,
            refused BOOLEAN NOT NULL DEFAULT FALSE,
            latency_ms INTEGER,
            model TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT web_messages_role CHECK (role IN ('user', 'assistant'))
        );
        CREATE INDEX IF NOT EXISTS idx_web_messages_conversation
            ON web_messages(conversation_id, created_at);
        """,
    ),
]


async def apply_migrations(pool: asyncpg.Pool) -> list[str]:
    """Apply pending migrations; safe to call from several workers."""
    applied: list[str] = []
    async with pool.acquire() as conn:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        await conn.execute("SELECT pg_advisory_lock($1)", LOCK_KEY)
        try:
            known = {
                row["version"] for row in await conn.fetch("SELECT version FROM schema_migrations")
            }
            for version, sql in MIGRATIONS:
                if version in known:
                    continue
                async with conn.transaction():
                    await conn.execute(sql)
                    await conn.execute(
                        "INSERT INTO schema_migrations(version) VALUES($1) "
                        "ON CONFLICT (version) DO NOTHING",
                        version,
                    )
                applied.append(version)
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", LOCK_KEY)
    return applied
