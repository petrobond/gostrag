import asyncio
import json

import httpx
import pytest

from app.config import Settings
from app.embeddings.cloudru import CloudRuEmbedder, CloudRuError
from app.embeddings.factory import get_embedder


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("CLOUDRU_API_KEY", "test-key")
    monkeypatch.setenv("CLOUDRU_BASE_URL", "https://cloudru.test/v1")
    monkeypatch.setenv("CLOUDRU_BATCH_SIZE", "2")
    monkeypatch.setenv("CLOUDRU_MAX_RETRIES", "2")
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    return Settings(_env_file=None)


def vector(value: float = 0.1) -> list[float]:
    return [value] * 1024


def test_embed_documents_splits_batches_and_keeps_order(settings):
    calls: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        calls.append(payload["input"])
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": index, "embedding": vector(float(index))}
                    for index, _ in enumerate(payload["input"])
                ]
            },
        )

    embedder = CloudRuEmbedder(settings, transport=httpx.MockTransport(handler))
    vectors = asyncio.run(embedder.aembed_documents(["a", "b", "c"]))

    assert calls == [["a", "b"], ["c"]]
    assert len(vectors) == 3
    assert vectors[0][0] == 0.0
    assert vectors[1][0] == 1.0
    assert vectors[2][0] == 0.0


def test_retry_on_rate_limit(settings, monkeypatch):
    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("app.embeddings.cloudru.sleep", no_sleep)
    responses = [429, 200]
    calls: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        calls.append(1)
        status = responses.pop(0)
        if status == 429:
            return httpx.Response(429, json={"message": "rate limit"})
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": vector()}]})

    embedder = CloudRuEmbedder(settings, transport=httpx.MockTransport(handler))
    result = asyncio.run(embedder.aembed_query("вопрос"))

    assert len(result) == 1024
    assert len(calls) == 2


def test_auth_error_is_not_retried(settings):
    calls: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(401, json={"message": "Missing authorization in request"})

    embedder = CloudRuEmbedder(settings, transport=httpx.MockTransport(handler))

    with pytest.raises(CloudRuError) as error:
        asyncio.run(embedder.aembed_query("вопрос"))

    assert error.value.status == 401
    assert len(calls) == 1


def test_missing_credentials_raises(monkeypatch):
    monkeypatch.delenv("CLOUDRU_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        CloudRuEmbedder(Settings(_env_file=None))


def test_factory_selects_cloudru(settings, monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "cloudru")
    embedder = get_embedder(Settings(_env_file=None))
    assert isinstance(embedder, CloudRuEmbedder)
    assert embedder.dim == 1024
