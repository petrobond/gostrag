from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from app.llm.chain import LLMChain, classify
from app.rag.prompts import SYSTEM_PROMPT, USER_TEMPLATE, format_documents

JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass(slots=True)
class Citation:
    gost: str
    clause: str
    page: int
    quote: str = ""
    valid: bool = False


@dataclass(slots=True)
class Answer:
    answer: str
    citations: list[Citation] = field(default_factory=list)
    confidence: float = 0.0
    refused: bool = False
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
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = JSON_RE.search(cleaned)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
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

        allowed = {(c["gost_number"], c["clause"]) for c in chunks}
        citations: list[Citation] = []
        for item in data.get("citations", []) or []:
            citation = Citation(
                gost=str(item.get("gost", "")),
                clause=str(item.get("clause", "")),
                page=int(item.get("page", 0) or 0),
                quote=str(item.get("quote", "")),
            )
            citation.valid = (citation.gost, citation.clause) in allowed
            citations.append(citation)

        return Answer(
            answer=str(data.get("answer", result.content)),
            citations=citations,
            confidence=float(data.get("confidence", 0.0) or 0.0),
            refused=bool(data.get("refused", False)),
            missing=[str(x) for x in (data.get("missing", []) or [])],
            model=result.model,
            provider=result.provider,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            raw=result.content,
        )
