from __future__ import annotations

import asyncio
from asyncio import sleep

import httpx

from app.config import Settings


class CloudRuReranker:
    """Cloud.ru /score reranker (BAAI/bge-reranker-v2-m3)."""

    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not settings.cloudru_api_key:
            raise RuntimeError("CLOUDRU_API_KEY is not configured")
        self.api_key = settings.cloudru_api_key
        self.url = settings.cloudru_rerank_url
        self.model = settings.cloudru_rerank_model
        self.timeout = settings.cloudru_rerank_timeout_sec
        self.retries = max(1, settings.cloudru_max_retries)
        self._transport = transport
        self.last_tokens = 0

    async def ascore(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout, transport=self._transport
                ) as client:
                    response = await client.post(
                        self.url,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                            "Accept": "application/json",
                        },
                        json={
                            "model": self.model,
                            "encoding_format": "float",
                            "text_1": query,
                            "text_2": documents,
                        },
                    )
            except httpx.TransportError as exc:
                last_error = exc
                if attempt >= self.retries:
                    raise
                await sleep(min(2**attempt, 8))
                continue
            if response.status_code == 200:
                payload = response.json()
                usage = payload.get("usage", {})
                self.last_tokens = int(usage.get("total_tokens", 0) or 0)
                rows = sorted(payload.get("data", []), key=lambda row: row.get("index", 0))
                scores = [float(row["score"]) for row in rows]
                if len(scores) != len(documents):
                    raise RuntimeError(
                        f"reranker returned {len(scores)} scores for {len(documents)} documents"
                    )
                return scores
            last_error = RuntimeError(
                f"reranker HTTP {response.status_code}: {response.text[:300]}"
            )
            if response.status_code in (429, 500, 502, 503, 504) and attempt < self.retries:
                await sleep(min(2**attempt, 8))
                continue
            raise last_error
        raise RuntimeError(f"reranker request failed: {last_error}")

    def score(self, query: str, documents: list[str]) -> list[float]:
        return asyncio.run(self.ascore(query, documents))
