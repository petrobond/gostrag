from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.embeddings.base import Embedder
from app.rag.chunk_store import ChunkStore
from app.retrieval.bm25 import BM25Index
from app.retrieval.fusion import rrf
from app.storage.qdrant import QdrantStore


@dataclass(slots=True)
class RetrievedChunk:
    chunk_id: str
    text: str
    gost_number: str
    clause: str
    section: str
    section_title: str
    page: int
    score: float
    doc_id: str


class Retriever:
    def __init__(
        self,
        settings: Settings,
        embedder: Embedder,
        bm25: BM25Index,
        qdrant: QdrantStore,
        chunks: ChunkStore,
    ) -> None:
        self.settings = settings
        self.embedder = embedder
        self.bm25 = bm25
        self.qdrant = qdrant
        self.chunks = chunks

    async def retrieve(
        self,
        query: str,
        top_k: int = 6,
        gost_number: str | None = None,
    ) -> list[RetrievedChunk]:
        dense_hits = await self.qdrant.search(
            self.embedder.embed_query(query), limit=20, gost_number=gost_number
        )
        bm25_hits = self.bm25.search(query, top_k=20)
        fused = rrf(
            [[hit.chunk_id for hit in dense_hits], [hit.chunk_id for hit in bm25_hits]],
            top_n=top_k,
        )
        result: list[RetrievedChunk] = []
        for chunk_id, score in fused:
            payload = self.chunks.get(chunk_id)
            if not payload:
                continue
            result.append(
                RetrievedChunk(
                    chunk_id=chunk_id,
                    text=payload["text"],
                    gost_number=payload["gost_number"],
                    clause=payload["clause"],
                    section=payload.get("section", ""),
                    section_title=payload.get("section_title", ""),
                    page=int(payload.get("page", 0)),
                    score=score,
                    doc_id=payload["doc_id"],
                )
            )
        return result
