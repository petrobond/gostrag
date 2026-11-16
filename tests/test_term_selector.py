import asyncio

from app.llm.chain import LLMResult
from app.rag.term_catalog import TermCatalog
from app.rag.term_selector import TermSelector

ROWS = [
    {
        "gost_number": "ГОСТ Р 71476—2024",
        "clause": "3.1.1",
        "clause_title": "агент ИИ (AI agent):",
        "text": "агент ИИ (AI agent): Автоматически действующий объект.",
        "page": 5,
        "chunk_type": "clause",
        "provenance": {"file": "doc.pdf"},
    },
    {
        "gost_number": "ГОСТ Р 71476—2024",
        "clause": "3.1.4",
        "clause_title": "система ИИ (AI system):",
        "text": "система ИИ (AI system): Техническая система.",
        "page": 5,
        "chunk_type": "clause",
        "provenance": {"file": "doc.pdf"},
    },
]


class FakeChain:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = []

    async def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return LLMResult(
            content=self.content,
            model="fake-llm",
            provider="fake",
            tokens_in=10,
            tokens_out=5,
        )


def test_selector_accepts_only_catalog_clauses():
    catalog = TermCatalog(ROWS)
    chain = FakeChain(
        '{"criteria": "system-level", "selected": ['
        '{"clause": "3.1.4", "reason": "system"},'
        '{"clause": "9.9.9", "reason": "invented"}]}'
    )
    result = asyncio.run(
        TermSelector(None, chain).select(
            "Какие термины характеризуют систему?", "ГОСТ Р 71476—2024", catalog.for_gost("ГОСТ Р 71476—2024")
        )
    )
    assert [term.clause for term in result.terms] == ["3.1.4"]
    assert result.model == "fake-llm"
    assert not result.fallback
    assert result.criteria == "system-level"


def test_selector_falls_back_when_llm_returns_no_valid_terms():
    catalog = TermCatalog(ROWS)
    chain = FakeChain('{"selected": [{"clause": "9.9.9"}]}')
    result = asyncio.run(
        TermSelector(None, chain).select(
            "Какие термины относятся к системе?", "ГОСТ Р 71476—2024", catalog.for_gost("ГОСТ Р 71476—2024")
        )
    )
    assert len(result.terms) == 2
    assert result.fallback
