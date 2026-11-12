from __future__ import annotations

import asyncio

from app.config import Settings
from app.llm.gigachat import GigaChatClient


class GigaChatEmbedder:
    """GigaChat embeddings (paid; 402 if no paid tokens)."""

    dim = 2048

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = GigaChatClient(settings)

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), 16):
            batch = texts[start : start + 16]
            vectors.extend(await self.client.embeddings(self.settings.gigachat_embedding_model, batch))
        return vectors

    async def aembed_query(self, text: str) -> list[float]:
        return (await self.aembed_documents([text]))[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return asyncio.run(self.aembed_documents(texts))

    def embed_query(self, text: str) -> list[float]:
        return asyncio.run(self.aembed_query(text))
