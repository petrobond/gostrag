from __future__ import annotations

import asyncio

from fastembed import TextEmbedding


class LocalE5Embedder:
    """Local multilingual-e5-large via ONNX Runtime (no GPU, no API)."""

    dim = 1024

    def __init__(
        self,
        model_name: str = "intfloat/multilingual-e5-large",
        cache_dir: str | None = None,
        threads: int | None = None,
    ) -> None:
        self.model = TextEmbedding(
            model_name=model_name,
            cache_dir=cache_dir or None,
            threads=threads,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, vector)) for vector in self.model.embed(texts, batch_size=16)]

    def embed_query(self, text: str) -> list[float]:
        return list(map(float, next(iter(self.model.query_embed(text)))))

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self.embed_documents, texts)

    async def aembed_query(self, text: str) -> list[float]:
        return await asyncio.to_thread(self.embed_query, text)
