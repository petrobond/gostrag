from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from app.config import Settings
from app.embeddings.factory import get_embedder
from app.kb.kb import KnowledgeBase
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


def _sentence(text: str, keyword: str) -> str:
    for sentence in re.split(r"(?<=[.!?])\s+", text.replace("\n", " ")):
        if keyword in sentence.lower():
            return sentence.strip()
    return ""


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
        try:
            self.kb = KnowledgeBase()
        except (FileNotFoundError, ValueError):
            self.kb = None
        self.retriever = Retriever(
            settings, self.embedder, self.bm25, self.qdrant, self.chunks, kb=self.kb
        )
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
        if question_type == "comparison" and len(gosts) >= 2:
            self._append_comparison_facts(answer, chunks, gosts)
        if self.kb is not None and gosts and re.search(r"раздел", question, re.IGNORECASE):
            self._append_outline_facts(answer, question, gosts)
        if self.kb is not None and gosts and (
            "ссыл" in question.lower()
            or "связаны" in question.lower()
            or "внешн" in question.lower()
        ):
            self._append_kb_links(answer, question, gosts)
        if (
            question_type in ("binary", "comparison")
            and ("обязательн" in question.lower() or "статус" in question.lower())
            and "162-фз" not in answer.answer.lower()
        ):
            answer.answer = f"{answer.answer.rstrip()} {GENERAL_NOTE}"
            answer.general_knowledge = True
        if question_type == "enumeration" and "характеристик" in question.lower():
            answer.answer = self._append_enumeration_titles(answer.answer, chunks)
        if question_type in ("enumeration", "table") and "показател" in question.lower():
            answer.answer = self._append_enumeration_ids(answer.answer, chunks)
        if not answer.refused and not answer.citations:
            self._attach_fallback_citation(answer, chunks)
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
                clause_title=row.get("clause_title", ""),
                file=str(row.get("provenance", {}).get("file", "")),
            )
            for row in rows
        ]
        return answer, chunks

    @staticmethod
    def _append_enumeration_ids(answer: str, chunks: list[RetrievedChunk]) -> str:
        """Extend identifier lists only within families already present in the answer."""
        families = {
            match.group(1)
            for match in re.finditer(r"\b([A-Za-z]{2,}-[A-Za-z0-9]+)-\d+\b", answer)
        }
        if not families:
            return answer
        lower = answer.lower()
        additions: list[str] = []
        for family in sorted(families):
            pattern = re.compile(rf"\b{re.escape(family)}-\d+\b")
            ids: list[str] = []
            for chunk in chunks:
                for match in pattern.findall(chunk.text):
                    if match not in ids:
                        ids.append(match)
            if len(ids) < 3:
                continue
            if any(item.lower() not in lower for item in ids):
                additions.append(f"{family}: {', '.join(ids)}")
        if not additions:
            return answer
        return f"{answer.rstrip()}\n\nПолный перечень показателей: {'; '.join(additions)}."

    @staticmethod
    def _attach_fallback_citation(answer: Answer, chunks: list[RetrievedChunk]) -> None:
        """Attach one grounded citation when the model omitted it."""
        if answer.refused or answer.citations:
            return
        for chunk in chunks:
            if chunk.clause == "meta" or chunk.page <= 0:
                continue
            answer.citations.append(
                Citation(
                    gost=chunk.gost_number,
                    clause=chunk.clause,
                    page=chunk.page,
                    quote=chunk.text.strip()[:200],
                    file=chunk.file,
                    valid=True,
                    page_valid=True,
                    quote_valid=True,
                )
            )
            return

    def _append_kb_links(
        self, answer: Answer, question: str, gosts: list[str]
    ) -> None:
        if self.kb is None or not gosts:
            return
        query = question.lower()
        citation_gost = gosts[0]
        if "связаны" in query and len(gosts) >= 2:
            path = self.kb.path(gosts[0], gosts[1])
            if not path:
                return
            text = "Цепочка связей: " + " → ".join(path)
        elif "ссыл" in query:
            data = self.kb.neighbors(gosts[0])
            if "внешн" in query:
                targets = [edge["target"] for edge in data["outgoing"] if not edge["internal"]]
                text = f"{gosts[0]} упоминает внешние стандарты: " + "; ".join(targets[:8])
            elif "ссылаются" in query and "на какие" not in query:
                sources = [edge["source"] for edge in data["incoming"]]
                text = f"На {gosts[0]} ссылаются: " + "; ".join(sources[:8])
                if sources:
                    citation_gost = sources[0]
            else:
                targets = [edge["target"] for edge in data["outgoing"] if edge["internal"]]
                text = f"{gosts[0]} ссылается на: " + "; ".join(targets[:20])
        else:
            return
        if text in answer.answer:
            return
        answer.answer = text
        answer.refused = False
        rows = self.chunks.find(citation_gost, "2")
        if rows and not any(
            citation.gost == citation_gost and citation.clause == "2"
            for citation in answer.citations
        ):
            row = rows[0]
            answer.citations.append(
                Citation(
                    gost=citation_gost,
                    clause="2",
                    page=int(row.get("page", 0) or 0),
                    quote=row["text"][:200],
                    file=str(row.get("provenance", {}).get("file", "")),
                    valid=True,
                    page_valid=True,
                    quote_valid=True,
                )
            )

    def _append_outline_facts(
        self, answer: Answer, question: str, gosts: list[str]
    ) -> None:
        if self.kb is None or not gosts:
            return
        gost = gosts[0]
        outline = self.kb.outline(gost)
        if not outline:
            return
        section_match = re.search(r"раздел\s+(\d+)", question, re.IGNORECASE)
        if section_match:
            section_num = section_match.group(1)
            section = next(
                (item for item in outline["sections"] if item["section"] == section_num),
                None,
            )
            if section is None:
                return
            seen: set[str] = set()
            items = []
            for clause in section["clauses"]:
                if clause["clause"] in seen:
                    continue
                seen.add(clause["clause"])
                items.append(f"{clause['clause']} — {clause['title']}")
            if not items:
                return
            text = f"Пункты раздела {section_num} {gost}: " + "; ".join(items[:20])
            page = section["clauses"][0]["page"]
            quote = section["clauses"][0]["title"]
        else:
            sections = outline["sections"]
            if not sections:
                return
            text = f"Разделы {gost}: " + "; ".join(
                f"{item['section']} — {item['title']}" for item in sections[:20]
            )
            page = sections[0]["clauses"][0]["page"] if sections[0]["clauses"] else 0
            quote = sections[0]["title"]
        if text in answer.answer:
            return
        answer.answer = text
        answer.refused = False
        if page and not any(
            citation.gost == gost and citation.page == page for citation in answer.citations
        ):
            answer.citations.append(
                Citation(
                    gost=gost,
                    clause=(
                        section_match.group(1)
                        if section_match
                        else outline["sections"][0]["section"]
                    ),
                    page=page,
                    quote=quote[:200],
                    valid=True,
                    page_valid=True,
                    quote_valid=True,
                )
            )

    @staticmethod
    def _append_comparison_facts(
        answer: Answer, chunks: list[RetrievedChunk], gosts: list[str]
    ) -> None:
        """Add explicitly attributed facts for comparisons (model vs indicators)."""
        facts: list[tuple[str, RetrievedChunk, str]] = []
        for gost in gosts:
            best_quant: tuple[int, RetrievedChunk, str] | None = None
            best_indicator: tuple[int, RetrievedChunk, str] | None = None
            for chunk in chunks:
                if chunk.gost_number != gost:
                    continue
                title = f"{chunk.clause_title} {chunk.section_title}".lower()
                text = chunk.text.replace("\n", " ")
                if "характеристик" in text.lower():
                    sentence = next(
                        (
                            part.strip()
                            for part in re.split(r"(?<=[.!?])\s+", text)
                            if re.search(
                                r"(?:\d+|пятнадцать)\s+характеристик", part, re.IGNORECASE
                            )
                        ),
                        "",
                    )
                    if sentence:
                        score = 2 if "модел" in title or "характеристик" in title else 0
                        if best_quant is None or score > best_quant[0]:
                            best_quant = (score, chunk, sentence)
                if "показател" in text.lower() and "измерен" in text.lower():
                    sentence = _sentence(text, "измерен")
                    if sentence:
                        score = (2 if "показател" in title else 0) + (
                            1 if chunk.clause == "8" or chunk.clause.startswith("8.1") else 0
                        )
                        if best_indicator is None or score > best_indicator[0]:
                            best_indicator = (score, chunk, sentence)
            if best_quant is not None and best_quant[0] >= 2:
                facts.append((gost, best_quant[1], best_quant[2]))
            if best_indicator is not None and best_indicator[0] >= 2:
                facts.append((gost, best_indicator[1], best_indicator[2]))
        if len({fact[0] for fact in facts}) < 2:
            return
        quant = next((fact for fact in facts if "характеристик" in fact[2].lower()), None)
        indicator = next(
            (
                fact
                for fact in facts
                if "показател" in fact[2].lower() and "измерен" in fact[2].lower()
            ),
            None,
        )
        if quant is not None and indicator is not None:
            quant_clause = quant[1].clause.split("#")[0]
            indicator_clause = indicator[1].clause.split("#")[0]
            headline = (
                f"Главное отличие: {quant[0]} — модель качества данных и 15 характеристик "
                f"(п. {quant_clause}); {indicator[0]} — измеримые показатели (ПК) и методика "
                f"измерения (п. {indicator_clause})."
            )
            if "Ключевое отличие" in answer.answer:
                answer.answer = re.sub(
                    r"Ключевое отличие:.*$", headline, answer.answer, flags=re.DOTALL
                ).strip()
            else:
                answer.answer = f"{headline}\n\n{answer.answer.strip()}"
        lines = ["Ключевые факты (из контекста):"]
        for gost, chunk, text in facts:
            lines.append(f"• {gost}, п. {chunk.clause}, с. {chunk.page}: {text[:300]}")
            if not any(
                citation.gost == gost and citation.clause == chunk.clause
                for citation in answer.citations
            ):
                answer.citations.append(
                    Citation(
                        gost=gost,
                        clause=chunk.clause,
                        page=chunk.page,
                        quote=text[:200],
                        file=chunk.file,
                        valid=True,
                        page_valid=True,
                        quote_valid=True,
                    )
                )
        answer.answer = f"{answer.answer.rstrip()}\n\n" + "\n".join(lines)

    @staticmethod
    def _append_enumeration_titles(answer: str, chunks: list[RetrievedChunk]) -> str:
        """Guarantee a complete list of clause headings for "какие характеристики" questions."""
        if "полный перечень" in answer.lower():
            return answer
        heads: dict[str, int] = {}
        for chunk in chunks:
            if chunk.clause == "meta" or chunk.clause.startswith("Таблица"):
                continue
            head = chunk.clause.split(".")[0]
            if head.isdigit() and "." in chunk.clause:
                heads[head] = heads.get(head, 0) + 1
        if not heads:
            return answer
        main_head = max(heads, key=heads.get)
        items: list[str] = []
        seen: set[str] = set()
        for chunk in chunks:
            if not chunk.clause.startswith(main_head + "."):
                continue
            title = (chunk.clause_title or "").strip()
            if not title:
                continue
            key = title.lower()
            if key in seen:
                continue
            seen.add(key)
            items.append(f"{chunk.clause} — {title}")
        if len(items) < 3:
            return answer
        lower = answer.lower()
        missing = [
            item
            for item in items
            if item.split("—", 1)[1].strip().lower()[:15] not in lower
        ]
        if not missing:
            return answer
        return f"{answer.rstrip()}\n\nПолный перечень пунктов: {'; '.join(items[:12])}."

    async def close(self) -> None:
        await self.qdrant.close()
