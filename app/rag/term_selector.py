"""LLM-assisted selection of a semantic subset of catalog terms."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field

from app.embeddings.base import Embedder
from app.llm.chain import LLMChain
from app.rag.term_catalog import CorpusTerm, norm_gost

JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

SYSTEM_PROMPT = """Ты — селектор терминов из каталога ГОСТа.
Выбери только те термины из списка кандидатов, которые отвечают критерию вопроса.
Не добавляй термины, которых нет в списке. Не придумывай номера пунктов.
Если criterion неоднозначен, выбери наиболее близкие термины и кратко объясни критерий.
Верни строго JSON:
{"criteria": "...", "selected": [{"clause": "3.1.4", "reason": "..."}]}
"""


@dataclass(slots=True)
class SelectionResult:
    terms: list[CorpusTerm] = field(default_factory=list)
    model: str = "rules"
    provider: str = "rules"
    tokens_in: int = 0
    tokens_out: int = 0
    fallback: bool = False
    criteria: str = ""
    raw: str = ""


def _parse_json(text: str) -> dict:
    match = JSON_OBJECT_RE.search(text or "")
    if not match:
        return {}
    try:
        data = json.loads(match.group(0), strict=False)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    norm_left = math.sqrt(sum(a * a for a in left))
    norm_right = math.sqrt(sum(b * b for b in right))
    if not norm_left or not norm_right:
        return 0.0
    return dot / (norm_left * norm_right)


class TermSelector:
    def __init__(self, embedder: Embedder | None, chain: LLMChain) -> None:
        self.embedder = embedder
        self.chain = chain
        self._vectors: dict[tuple[str, str], list[float]] = {}

    async def ranked(
        self, question: str, terms: list[CorpusTerm], limit: int = 25
    ) -> list[CorpusTerm]:
        if not self.embedder or len(terms) <= limit:
            return terms[:limit]
        try:
            missing = [
                term
                for term in terms
                if (norm_gost(term.gost_number), term.clause) not in self._vectors
            ]
            if missing:
                texts = [f"{term.term}. {term.definition}" for term in missing]
                vectors = await self.embedder.aembed_documents(texts)
                for term, vector in zip(missing, vectors, strict=False):
                    self._vectors[(norm_gost(term.gost_number), term.clause)] = vector
            vector = await self.embedder.aembed_query(question)
        except Exception:
            return terms[:limit]
        ranked = [
            (
                _cosine(
                    vector,
                    self._vectors.get((norm_gost(term.gost_number), term.clause), []),
                ),
                term,
            )
            for term in terms
        ]
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [term for _, term in ranked[:limit]]

    async def select(
        self, question: str, gost_number: str, terms: list[CorpusTerm], limit: int = 25
    ) -> SelectionResult:
        candidates = await self.ranked(question, terms, limit=limit)
        if not candidates:
            return SelectionResult()
        payload = [
            {
                "clause": term.clause,
                "term": term.term,
                "definition": term.definition[:350],
            }
            for term in candidates
        ]
        user = (
            f"Вопрос: {question}\n"
            f"ГОСТ: {gost_number}\n"
            "Кандидаты (только они доступны):\n"
            f"{json.dumps(payload, ensure_ascii=False)}\n"
            "Верни JSON по схеме."
        )
        try:
            result = await self.chain.chat(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user},
                ],
                complexity="complex",
                max_tokens=900,
                temperature=0.0,
            )
        except Exception:
            return SelectionResult(
                terms=candidates[:5],
                fallback=True,
                criteria="fallback: top semantic candidates",
            )
        data = _parse_json(result.content)
        by_clause = {term.clause: term for term in candidates}
        selected: list[CorpusTerm] = []
        for item in data.get("selected", []) or []:
            if not isinstance(item, dict):
                continue
            term = by_clause.get(str(item.get("clause") or ""))
            if term and term not in selected:
                selected.append(term)
            if len(selected) >= 8:
                break
        if not selected:
            return SelectionResult(
                terms=candidates[:5],
                model=result.model,
                provider=result.provider,
                tokens_in=result.tokens_in,
                tokens_out=result.tokens_out,
                fallback=True,
                criteria=str(data.get("criteria") or "fallback: top semantic candidates"),
                raw=result.content,
            )
        return SelectionResult(
            terms=selected,
            model=result.model,
            provider=result.provider,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            criteria=str(data.get("criteria") or ""),
            raw=result.content,
        )
