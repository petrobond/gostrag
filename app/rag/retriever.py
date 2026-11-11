from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import Settings
from app.embeddings.base import Embedder
from app.rag.chunk_store import ChunkStore
from app.retrieval.bm25 import BM25Index
from app.retrieval.fusion import rrf
from app.storage.qdrant import QdrantStore

GOST_RE = re.compile(r"(ГОСТ\s*Р|ПНСТ)\s*(\d+(?:\.\d+)?)\s*[—–-]\s*(\d{4})", re.IGNORECASE)
CLAUSE_RE = re.compile(r"(?:п\.?|пункт)\s*(\d+(?:\.\d+)+)", re.IGNORECASE)


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
        exact_gost, exact_clause = self._extract_reference(query, gost_number)
        exact: list[dict] = []
        if exact_gost and exact_clause:
            exact = self.chunks.find_fuzzy(exact_gost, exact_clause)

        dense_hits = await self.qdrant.search(
            self.embedder.embed_query(query), limit=20, gost_number=exact_gost
        )
        bm25_hits = self.bm25.search(query, top_k=40)
        if exact_gost:
            filtered = []
            for hit in bm25_hits:
                payload = self.chunks.get(hit.chunk_id)
                if payload and payload["gost_number"] == exact_gost:
                    filtered.append(hit)
            bm25_hits = filtered[:20]
        fused = rrf(
            [[hit.chunk_id for hit in dense_hits], [hit.chunk_id for hit in bm25_hits]],
            top_n=top_k,
        )
        result: list[RetrievedChunk] = []
        seen: set[str] = set()
        for row in exact:
            result.append(self._to_chunk(row, 1.0))
            seen.add(row["chunk_id"])
        for chunk_id, score in fused:
            if chunk_id in seen:
                continue
            payload = self.chunks.get(chunk_id)
            if not payload:
                continue
            result.append(self._to_chunk(payload, score))
        return result[: max(top_k, len(exact))]

    @staticmethod
    def _extract_reference(query: str, gost_number: str | None) -> tuple[str | None, str | None]:
        gost = gost_number
        match = GOST_RE.search(query)
        if match:
            gost = f"{match.group(1).upper().replace('ГОСТР', 'ГОСТ Р')} {match.group(2)}—{match.group(3)}"
        clause_match = CLAUSE_RE.search(query)
        clause = clause_match.group(1) if clause_match else None
        return gost, clause

    @staticmethod
    def _to_chunk(payload: dict, score: float) -> RetrievedChunk:
        return RetrievedChunk(
            chunk_id=payload["chunk_id"],
            text=payload["text"],
            gost_number=payload["gost_number"],
            clause=payload["clause"],
            section=payload.get("section", ""),
            section_title=payload.get("section_title", ""),
            page=int(payload.get("page", 0)),
            score=score,
            doc_id=payload["doc_id"],
        )
