from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from app.llm.chain import LLMChain, classify
from app.rag.prompts import SYSTEM_PROMPT, USER_TEMPLATE, format_documents

JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
WS_RE = re.compile(r"\s+")
CLAUSE_IN_TEXT_RE = re.compile(r"(\d+(?:\.\d+){1,4})")
APPENDIX_IN_TEXT_RE = re.compile(r"приложение\s+([А-ЯA-Z]{1,2})", re.IGNORECASE)
GOST_SEP_RE = re.compile(r"[\s—–-]+")


def _norm(text: str) -> str:
    return WS_RE.sub(" ", text.lower()).strip()


def _norm_gost(value: str) -> str:
    return GOST_SEP_RE.sub("", value or "").lower()


def _clause_key(value: str) -> str:
    """Extract a clause number or appendix letter from free-form model output."""
    appendix = APPENDIX_IN_TEXT_RE.search(value or "")
    if appendix:
        return f"Приложение {appendix.group(1).upper()}"
    match = CLAUSE_IN_TEXT_RE.search(value or "")
    return match.group(1) if match else (value or "").strip()


def _resolve_chunk(chunks: list[dict], gost: str, clause: str, quote: str) -> dict | None:
    """Map a model citation onto the chunk it actually refers to."""
    norm = _norm_gost(gost)
    same_doc = [chunk for chunk in chunks if _norm_gost(chunk["gost_number"]) == norm]
    if not same_doc and len(chunks) == 1:
        same_doc = chunks
    key = _clause_key(clause)
    for chunk in same_doc:
        if chunk["clause"] == key:
            return chunk
    for chunk in same_doc:
        if chunk["clause"].startswith(key + ".") or key.startswith(chunk["clause"] + "."):
            return chunk
    title_key = _norm(clause)
    if title_key:
        for chunk in same_doc:
            if title_key and title_key in _norm(chunk.get("clause_title", "")):
                return chunk
    if quote:
        norm_quote = _norm(quote)
        for chunk in same_doc:
            if norm_quote and norm_quote in _norm(chunk["text"]):
                return chunk
    return None


@dataclass(slots=True)
class Citation:
    gost: str
    clause: str
    page: int
    quote: str = ""
    file: str = ""
    valid: bool = False
    page_valid: bool = False
    quote_valid: bool = False


@dataclass(slots=True)
class Answer:
    answer: str
    citations: list[Citation] = field(default_factory=list)
    confidence: float = 0.0
    refused: bool = False
    general_knowledge: bool = False
    missing: list[str] = field(default_factory=list)
    model: str = ""
    provider: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    raw: str = ""


def _parse_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    candidates = [cleaned]
    match = JSON_RE.search(cleaned)
    if match:
        candidates.append(match.group(0))
    for candidate in candidates:
        try:
            data = json.loads(candidate, strict=False)
        except json.JSONDecodeError:
            continue
        if isinstance(data, str):
            try:
                data = json.loads(data, strict=False)
            except json.JSONDecodeError:
                continue
        if isinstance(data, dict):
            return data
    return {}


class Generator:
    def __init__(self, chain: LLMChain) -> None:
        self.chain = chain

    async def generate(self, question: str, chunks: list[dict]) -> Answer:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": USER_TEMPLATE.format(
                    documents=format_documents(chunks), question=question
                ),
            },
        ]
        result = await self.chain.chat(messages, complexity=classify(question))
        data = _parse_json(result.content)

        allowed: list[dict] = chunks
        citations: list[Citation] = []
        seen_keys: set[tuple[str, str]] = set()
        for item in data.get("citations", []) or []:
            gost = str(item.get("gost", ""))
            clause = str(item.get("clause", ""))
            quote = str(item.get("quote", ""))
            chunk = _resolve_chunk(allowed, gost, clause, quote)
            if chunk is None:
                citations.append(
                    Citation(
                        gost=gost,
                        clause=clause,
                        page=int(item.get("page", 0) or 0),
                        quote=quote,
                    )
                )
                continue
            key = (_norm_gost(chunk["gost_number"]), chunk["clause"])
            if key in seen_keys:
                continue
            seen_keys.add(key)
            citation = Citation(
                gost=chunk["gost_number"],
                clause=chunk["clause"],
                page=int(chunk.get("page", 0) or 0),
                quote=quote,
            )
            citation.file = str(chunk.get("file") or chunk.get("provenance", {}).get("file", ""))
            citation.page_valid = True
            citation.quote_valid = bool(quote) and _norm(quote) in _norm(chunk["text"])
            citation.valid = True
            citations.append(citation)

        return Answer(
            answer=str(data.get("answer", result.content)),
            citations=citations,
            confidence=float(data.get("confidence", 0.0) or 0.0),
            refused=bool(data.get("refused", False)),
            general_knowledge=bool(data.get("general_knowledge", False)),
            missing=[str(x) for x in (data.get("missing", []) or [])],
            model=result.model,
            provider=result.provider,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            raw=result.content,
        )
