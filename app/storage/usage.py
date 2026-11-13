"""PostgreSQL usage log for bot questions (qa_log + usage_daily)."""

from __future__ import annotations

import json
from typing import Any

import asyncpg


class UsageStore:
    def __init__(self, dsn: str, pool: Any | None = None) -> None:
        self.dsn = dsn
        self.pool = pool

    async def connect(self) -> None:
        if self.pool is None:
            self.pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=3, timeout=5)

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    async def log(
        self,
        user_id: int,
        question: str,
        answer: str,
        citations: list[dict],
        refused: bool,
        latency_ms: int,
        model: str = "",
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> None:
        if self.pool is None:
            return
        payload = json.dumps(citations, ensure_ascii=False)
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO users(user_id) VALUES($1) ON CONFLICT (user_id) DO NOTHING",
                user_id,
            )
            await conn.execute(
                "INSERT INTO qa_log"
                "(user_id, question, answer, citations, model, refused, latency_ms, tokens_in, tokens_out) "
                "VALUES($1, $2, $3, $4::jsonb, $5, $6, $7, $8, $9)",
                user_id,
                question[:2000],
                answer[:8000],
                payload,
                model,
                refused,
                latency_ms,
                tokens_in,
                tokens_out,
            )
            await conn.execute(
                "INSERT INTO usage_daily(user_id, day, questions, tokens_in, tokens_out) "
                "VALUES($1, CURRENT_DATE, 1, $2, $3) "
                "ON CONFLICT (user_id, day) DO UPDATE SET "
                "questions = usage_daily.questions + 1, "
                "tokens_in = usage_daily.tokens_in + EXCLUDED.tokens_in, "
                "tokens_out = usage_daily.tokens_out + EXCLUDED.tokens_out",
                user_id,
                tokens_in,
                tokens_out,
            )

    async def stats(self, days: int = 30) -> dict:
        if self.pool is None:
            return {}
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT count(*) AS questions, "
                "count(*) FILTER (WHERE refused) AS refusals, "
                "percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms) AS p50, "
                "percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95, "
                "coalesce(sum(tokens_in), 0) AS tokens_in, "
                "coalesce(sum(tokens_out), 0) AS tokens_out "
                "FROM qa_log WHERE created_at >= now() - ($1::int * interval '1 day')",
                days,
            )
            users = await conn.fetchval(
                "SELECT count(DISTINCT user_id) FROM qa_log "
                "WHERE created_at >= now() - ($1::int * interval '1 day')",
                days,
            )
        result = dict(row) if row else {}
        result["users"] = users or 0
        result["days"] = days
        result["p50"] = round(float(result.get("p50") or 0), 1)
        result["p95"] = round(float(result.get("p95") or 0), 1)
        return result
