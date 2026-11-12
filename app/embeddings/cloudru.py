from __future__ import annotations

import asyncio
from asyncio import sleep

import httpx

from app.config import Settings


class CloudRuError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"Cloud.ru HTTP {status}: {message}")
        self.status = status
        self.message = message


class CloudRuEmbedder:
    """Cloud.ru Foundation Models embeddings (OpenAI-compatible /v1/embeddings)."""

    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not settings.cloudru_api_key:
            raise RuntimeError("CLOUDRU_API_KEY is not configured")
        self.api_key = settings.cloudru_api_key
        self.base_url = settings.cloudru_base_url.rstrip("/")
        self.model = settings.cloudru_embedding_model
        self.dim = settings.cloudru_embedding_dim
        self.batch_size = max(1, settings.cloudru_batch_size)
        self.timeout = settings.cloudru_timeout_sec
        self.retries = max(1, settings.cloudru_max_retries)
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self.timeout, transport=self._transport)

    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                async with self._client() as client:
                    response = await client.post(
                        f"{self.base_url}/embeddings",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                            "Accept": "application/json",
                        },
                        json={"model": self.model, "input": texts},
                    )
            except httpx.TransportError as exc:
                last_error = exc
                if attempt >= self.retries:
                    raise
                await sleep(min(2**attempt, 8))
                continue

            if response.status_code == 200:
                data = response.json()
                rows = sorted(data.get("data", []), key=lambda row: row.get("index", 0))
                vectors = [list(map(float, row["embedding"])) for row in rows]
                if len(vectors) != len(texts):
                    raise CloudRuError(
                        200,
                        f"expected {len(texts)} embeddings, got {len(vectors)}",
                    )
                return vectors

            last_error = CloudRuError(response.status_code, response.text[:300])
            if response.status_code in (429, 500, 502, 503, 504) and attempt < self.retries:
                await sleep(min(2**attempt, 8))
                continue
            raise last_error
        raise RuntimeError(f"embeddings request failed: {last_error}")

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            vectors.extend(await self._embed_batch(batch))
        return vectors

    async def aembed_query(self, text: str) -> list[float]:
        return (await self._embed_batch([text]))[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return asyncio.run(self.aembed_documents(texts))

    def embed_query(self, text: str) -> list[float]:
        return asyncio.run(self.aembed_query(text))
