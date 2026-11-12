from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import Settings
from app.embeddings.base import Embedder
from app.rag.chunk_store import ChunkStore
from app.rag.query_classifier import (
    classify_question,
    extract_appendix,
    extract_comparison_entities,
    extract_term,
)
from app.retrieval.bm25 import BM25Index
from app.retrieval.fusion import rrf
from app.storage.qdrant import QdrantStore

GOST_RE = re.compile(r"(ГОСТ\s*Р|ПНСТ)\s*(\d+(?:\.\d+)?)\s*[—–-]\s*(\d{4})", re.IGNORECASE)
CLAUSE_RE = re.compile(r"(?:п\.?|пункт)\s*(\d+(?:\.\d+)+)", re.IGNORECASE)
LIST_MARKERS = ("какие", "перечисли", "этапы", "слои", "виды", "характеристики", "состав")


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
    clause_title: str = ""
    file: str = ""


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
        question_type = classify_question(query)
        exact: list[dict] = []
        if exact_gost and exact_clause:
            exact = self.chunks.find_fuzzy(exact_gost, exact_clause)
        elif question_type == "definition":
            exact = self.chunks.find_term(extract_term(query), exact_gost)
        elif question_type == "appendix" and exact_gost:
            appendix = extract_appendix(query)
            if appendix:
                exact = self.chunks.find_appendix(exact_gost, appendix)

        vector = await self.embedder.aembed_query(query)
        dense_hits = await self.qdrant.search(vector, limit=20, gost_number=exact_gost)
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
            seen.add(chunk_id)
        if result and question_type == "enumeration":
            self._expand_enumeration(query, result, seen, exact_gost, dense_hits)
        elif result and any(marker in query.lower() for marker in LIST_MARKERS):
            top = result[0]
            for row in self.chunks.section_chunks(top.doc_id, top.section):
                if row["chunk_id"] in seen:
                    continue
                result.append(self._to_chunk(row, 0.5))
                seen.add(row["chunk_id"])
                if len(result) >= 10:
                    break
        if question_type == "temporal" and exact_gost:
            for row in self.chunks.find_meta(exact_gost):
                if row["chunk_id"] in seen:
                    continue
                result.insert(0, self._to_chunk(row, 1.0))
                seen.add(row["chunk_id"])
        if question_type == "table" and exact_gost:
            added = 0
            for hit in self._bm25_in_doc(query, exact_gost, top_k=60):
                payload = self.chunks.get(hit.chunk_id)
                if not payload or payload.get("chunk_type") != "table" or hit.chunk_id in seen:
                    continue
                result.insert(0, self._to_chunk(payload, 0.85))
                seen.add(hit.chunk_id)
                added += 1
                if added >= 2:
                    break
        limit = max(top_k, len(exact))
        if question_type == "enumeration":
            limit = max(limit, self.ENUMERATION_RESULT_LIMIT)
        return result[:limit]

    ENUMERATION_GROUP_LIMIT = 16
    ENUMERATION_RESULT_LIMIT = 22

    def _expand_enumeration(
        self,
        query: str,
        result: list[RetrievedChunk],
        seen: set[str],
        exact_gost: str | None,
        dense_hits: list | None = None,
    ) -> None:
        """Put the whole clause group that enumerates items (4.1 ... 4.7) into context.

        The anchor is chosen by semantic similarity of the group (dense) with a BM25
        tie-break, so a question without a GOST number lands on the document the
        question is about, and the whole group is added before any secondary hits.
        """
        bm25_hits = (
            self._bm25_in_doc(query, exact_gost, top_k=100)
            if exact_gost
            else self.bm25.search(query, top_k=80)
        )
        anchors = self._enumeration_anchors(bm25_hits, result, exact_gost, dense_hits)
        per_group = self.ENUMERATION_GROUP_LIMIT if len(anchors) <= 1 else 10
        for doc_id, head in anchors:
            group = self._group_order(
                self.chunks.clause_siblings(doc_id, f"{head}.0", limit=40)
            )
            added = 0
            for row in group:
                if added >= per_group:
                    break
                if row["chunk_id"] in seen:
                    continue
                result.append(self._to_chunk(row, 0.6))
                seen.add(row["chunk_id"])
                added += 1
        ordered_hits = sorted(
            bm25_hits,
            key=lambda hit: (
                0
                if (self.chunks.get(hit.chunk_id) or {}).get("chunk_type") == "table"
                else 1
            ),
        )
        for hit in ordered_hits:
            if hit.chunk_id in seen:
                continue
            payload = self.chunks.get(hit.chunk_id)
            if not payload:
                continue
            result.append(self._to_chunk(payload, 0.4))
            seen.add(hit.chunk_id)
            if len(result) >= self.ENUMERATION_RESULT_LIMIT:
                break

    @staticmethod
    def _group_order(rows: list[dict]) -> list[dict]:
        """Shallow headings first: 8.3.3 is more useful than 8.2.1.1 for "какие слои"."""
        return sorted(rows, key=lambda row: row["clause"].count("."))

    def _enumeration_anchors(
        self,
        bm25_hits: list,
        result: list[RetrievedChunk],
        exact_gost: str | None,
        dense_hits: list | None = None,
        limit: int = 2,
    ) -> list[tuple[str, str]]:
        """Rank (doc_id, section) pairs by dense similarity plus BM25 support."""
        bm25_scores: dict[tuple[str, str], float] = {}
        dense_scores: dict[tuple[str, str], float] = {}
        for hit in bm25_hits:
            payload = self.chunks.get(hit.chunk_id)
            if not payload:
                continue
            if exact_gost and payload["gost_number"] != exact_gost:
                continue
            head = payload["clause"].split(".")[0]
            if not head.isdigit():
                continue
            key = (payload["doc_id"], head)
            bm25_scores[key] = bm25_scores.get(key, 0.0) + float(
                getattr(hit, "score", 0.0) or 0.0
            )
        for hit in dense_hits or []:
            payload = self.chunks.get(hit.chunk_id)
            if not payload:
                continue
            if exact_gost and payload["gost_number"] != exact_gost:
                continue
            head = payload["clause"].split(".")[0]
            if not head.isdigit():
                continue
            key = (payload["doc_id"], head)
            dense_scores[key] = max(dense_scores.get(key, 0.0), float(hit.score or 0.0))
        for chunk in result:
            head = chunk.clause.split(".")[0]
            if head.isdigit():
                key = (chunk.doc_id, head)
                dense_scores[key] = max(dense_scores.get(key, 0.0), float(chunk.score or 0.0))
        keys = set(bm25_scores) | set(dense_scores)
        if not keys:
            return []
        combined = {
            key: dense_scores.get(key, 0.0) + 0.0003 * bm25_scores.get(key, 0.0)
            for key in keys
        }
        ranked = sorted(combined.items(), key=lambda item: item[1], reverse=True)
        anchors = [ranked[0][0]]
        if not exact_gost and len(ranked) > 1 and ranked[1][1] >= 0.6 * ranked[0][1]:
            anchors.append(ranked[1][0])
        return anchors[:limit]


    async def retrieve_multi(
        self,
        query: str,
        gost_numbers: list[str],
        top_k: int = 4,
    ) -> list[RetrievedChunk]:
        """Multi-hop retrieval: separate search per GOST, then merge.

        Every standard contributes its scope clause, so a comparison always sees what
        each document is about even when the question words match body text only.
        """
        merged: list[RetrievedChunk] = []
        seen: set[str] = set()
        for gost in gost_numbers:
            for row in self.chunks.find(gost, "1")[:1]:
                if row["chunk_id"] in seen:
                    continue
                merged.append(self._to_chunk(row, 0.9))
                seen.add(row["chunk_id"])
            for chunk in await self.retrieve(query, top_k=top_k, gost_number=gost):
                if chunk.chunk_id in seen:
                    continue
                seen.add(chunk.chunk_id)
                merged.append(chunk)
        return merged

    async def retrieve_comparison(
        self,
        query: str,
        gost_numbers: list[str],
        top_k: int = 4,
    ) -> list[RetrievedChunk]:
        """Comparison retrieval: multi-hop for several standards, per-entity for one."""
        if len(gost_numbers) >= 2:
            return await self.retrieve_multi(query, gost_numbers, top_k=top_k)
        gost = gost_numbers[0] if gost_numbers else None
        entities = extract_comparison_entities(query)
        merged: list[RetrievedChunk] = []
        seen: set[str] = set()
        if not gost_numbers:
            for row in self.chunks.meta_by_doc_type():
                if row["chunk_id"] in seen:
                    continue
                merged.append(self._to_chunk(row, 1.0))
                seen.add(row["chunk_id"])
        for entity in entities:
            for row in self.chunks.find_term(entity, gost, limit=2):
                if row["chunk_id"] in seen:
                    continue
                merged.append(self._to_chunk(row, 1.0))
                seen.add(row["chunk_id"])
            for hit in self._bm25_in_doc(entity, gost, top_k=20)[:2]:
                if hit.chunk_id in seen:
                    continue
                merged.append(self._to_chunk(self.chunks.get(hit.chunk_id), 0.6))
                seen.add(hit.chunk_id)
        for chunk in await self.retrieve(query, top_k=top_k, gost_number=gost):
            if chunk.chunk_id in seen:
                continue
            merged.append(chunk)
            seen.add(chunk.chunk_id)
        return merged

    def _bm25_in_doc(self, query: str, gost: str | None, top_k: int = 40) -> list:
        hits = self.bm25.search(query, top_k=top_k)
        if not gost:
            return hits
        return [
            hit
            for hit in hits
            if (payload := self.chunks.get(hit.chunk_id))
            and payload["gost_number"] == gost
        ]

    @staticmethod
    def _extract_reference(query: str, gost_number: str | None) -> tuple[str | None, str | None]:
        # An explicitly passed GOST (multi-hop pass) must win over the first mention in
        # the question: comparisons name several standards and the query keeps all of them.
        gost = gost_number
        if not gost:
            match = GOST_RE.search(query)
            if match:
                gost = (
                    f"{match.group(1).upper().replace('ГОСТР', 'ГОСТ Р')} "
                    f"{match.group(2)}—{match.group(3)}"
                )
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
            clause_title=payload.get("clause_title", ""),
            file=str(payload.get("provenance", {}).get("file", "")),
        )
