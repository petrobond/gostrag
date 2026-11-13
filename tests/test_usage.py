import asyncio

from app.storage.usage import UsageStore


class FakeConn:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def execute(self, sql: str, *args) -> None:
        self.calls.append((sql, args))

    async def fetchrow(self, _sql: str, _days: int) -> dict:
        return {
            "questions": 2,
            "refusals": 1,
            "p50": 100.0,
            "p95": 200.0,
            "tokens_in": 10,
            "tokens_out": 20,
        }

    async def fetchval(self, _sql: str, _days: int) -> int:
        return 1


class Acquire:
    def __init__(self, conn: FakeConn) -> None:
        self.conn = conn

    async def __aenter__(self) -> FakeConn:
        return self.conn

    async def __aexit__(self, *_args) -> None:
        return None


class FakePool:
    def __init__(self) -> None:
        self.conn = FakeConn()

    def acquire(self) -> Acquire:
        return Acquire(self.conn)


def test_usage_log_and_stats():
    pool = FakePool()
    store = UsageStore("", pool=pool)

    asyncio.run(
        store.log(
            1,
            "вопрос",
            "ответ",
            [{"gost": "ГОСТ Р 71476—2024", "clause": "3.1", "page": 5}],
            False,
            123,
            "GigaChat-3-Ultra",
            10,
            20,
        )
    )
    assert len(pool.conn.calls) == 3
    assert "qa_log" in pool.conn.calls[1][0]
    assert "usage_daily" in pool.conn.calls[2][0]

    stats = asyncio.run(store.stats(days=7))
    assert stats["questions"] == 2
    assert stats["refusals"] == 1
    assert stats["p50"] == 100.0
    assert stats["p95"] == 200.0