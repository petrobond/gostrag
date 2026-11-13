import asyncio

from app.main import health


def test_health_contains_version_and_runtime_fields():
    data = asyncio.run(health())
    assert data["status"] == "ok"
    assert data["version"]
    assert "collection" in data
    assert "kb_ready" in data
    assert isinstance(data["index_ready"], bool)