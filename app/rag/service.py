from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from pathlib import Path

from app.config import Settings
from app.embeddings.factory import get_embedder
from app.llm.chain import LLMChain
from app.rag.chunk_store import ChunkStore
from app.rag.generator import Answer, Generator
from app.rag.retriever import Retriever, RetrievedChunk
from app.retrieval.bm25 import BM25Index
from app.storage.qdrant import QdrantStore


@dataclass(slots=True)
class AskResult:
    answer: Answer
    chunks: list[RetrievedChunk]
    latency_ms: int


class AskService:
    def __init__(
        self,
        settings: Settings,
        corpus_dir: Path,
        index_dir: Path,
        qdrant_url: str,
    ) -> None:
        self.settings = settings
        self.embedder = get_embedder(settings)
        self.bm25 = BM25Index.load(index_dir / "bm25.pkl")
        self.qdrant = QdrantStore(qdrant_url, settings.qdrant_collection)
        self.chunks = ChunkStore(corpus_dir)
        self.retriever = Retriever(settings, self.embedder, self.bm25, self.qdrant, self.chunks)
        self.generator = Generator(LLMChain(settings))

    async def ask(self, question: str, top_k: int | None = None) -> AskResult:
        started = time.perf_counter()
        chunks = await self.retriever.retrieve(question, top_k=top_k or self.settings.max_top_k)
        answer = await self.generator.generate(question, [asdict(chunk) for chunk in chunks])
        latency_ms = int((time.perf_counter() - started) * 1000)
        return AskResult(answer=answer, chunks=chunks, latency_ms=latency_ms)

    async def close(self) -> None:
        await self.qdrant.close()
