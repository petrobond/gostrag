from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from pathlib import Path

from app.config import Settings
from app.embeddings.factory import get_embedder
from app.llm.chain import LLMChain
from app.rag.chunk_store import ChunkStore
from app.rag.generator import Answer, Citation, Generator
from app.rag.query_classifier import classify_question, extract_clause, extract_gosts
from app.rag.retriever import RetrievedChunk, Retriever
from app.retrieval.bm25 import BM25Index
from app.storage.qdrant import QdrantStore

GENERAL_NOTE = (
    "Общие знания (вне корпуса): национальные стандарты (ГОСТ Р) применяются на добровольной "
    "основе, если иное не установлено законом (ст. 26 Федерального закона № 162-ФЗ "
    "«О стандартизации в Российской Федерации»)."
)


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
        question_type = classify_question(question)
        if question_type == "injection":
            answer = Answer(
                answer=(
                    "Извините, я не выполняю такие инструкции. "
                    "Могу ответить на вопросы по российским стандартам ИИ."
                ),
                refused=True,
                model="guard",
                provider="rules",
            )
            return AskResult(answer=answer, chunks=[], latency_ms=0)

        gosts = extract_gosts(question)
        if question_type == "clause_lookup":
            extracted = self._extract_clause_answer(question, gosts)
            if extracted is not None:
                answer, answer_chunks = extracted
                latency_ms = int((time.perf_counter() - started) * 1000)
                return AskResult(answer=answer, chunks=answer_chunks, latency_ms=latency_ms)
        if question_type == "comparison":
            chunks = await self.retriever.retrieve_comparison(question, gosts, top_k=4)
        else:
            chunks = await self.retriever.retrieve(question, top_k=top_k or self.settings.max_top_k)
        answer = await self.generator.generate(question, [asdict(chunk) for chunk in chunks])
        if (
            question_type in ("binary", "comparison")
            and ("обязательн" in question.lower() or "статус" in question.lower())
            and "162-фз" not in answer.answer.lower()
        ):
            answer.answer = f"{answer.answer.rstrip()} {GENERAL_NOTE}"
            answer.general_knowledge = True
        latency_ms = int((time.perf_counter() - started) * 1000)
        return AskResult(answer=answer, chunks=chunks, latency_ms=latency_ms)

    def _extract_clause_answer(
        self,
        question: str,
        gosts: list[str],
    ) -> tuple[Answer, list[RetrievedChunk]] | None:
        """Answer "что говорится в п. X" with a verbatim excerpt instead of generation."""
        clause = extract_clause(question)
        gost = gosts[0] if gosts else None
        if not clause or not gost:
            return None
        rows = [
            row
            for row in self.chunks.find_fuzzy(gost, clause)
            if row["clause"] == clause or row["clause"].startswith(clause + ".")
        ]
        if not rows:
            return None
        text = " ".join(row["text"].strip() for row in rows)[:1500]
        citations = [
            Citation(
                gost=row["gost_number"],
                clause=row["clause"],
                page=int(row.get("page", 0) or 0),
                quote=row["text"].strip()[:200],
                file=str(row.get("provenance", {}).get("file", "")),
                valid=True,
                page_valid=True,
                quote_valid=True,
            )
            for row in rows
        ]
        labels = ", ".join(row["clause"] for row in rows)
        answer = Answer(
            answer=f"В {rows[0]['gost_number']} п. {labels}: «{text}»",
            citations=citations,
            confidence=0.95,
            model="extractive",
            provider="rules",
        )
        chunks = [
            RetrievedChunk(
                chunk_id=row["chunk_id"],
                text=row["text"],
                gost_number=row["gost_number"],
                clause=row["clause"],
                section=row.get("section", ""),
                section_title=row.get("section_title", ""),
                page=int(row.get("page", 0) or 0),
                score=1.0,
                doc_id=row["doc_id"],
            )
            for row in rows
        ]
        return answer, chunks

    async def close(self) -> None:
        await self.qdrant.close()
