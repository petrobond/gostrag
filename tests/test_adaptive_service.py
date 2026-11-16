import asyncio
from types import SimpleNamespace

from app.rag.adaptive import AdaptivePlan
from app.rag.service import AskService
from app.rag.term_catalog import TermCatalog
from app.rag.term_selector import SelectionResult

ROWS = [
    {
        "gost_number": "ГОСТ Р 71476—2024",
        "clause": "3.1",
        "clause_title": "Термины, относящиеся к ИИ",
        "text": "heading",
        "page": 5,
        "chunk_type": "clause",
        "provenance": {"file": "doc.pdf"},
    },
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


class Resolver:
    def resolve_query(self, question):
        return question


class Selector:
    def __init__(self):
        self.calls = []

    async def select(self, question, gost_number, terms):
        self.calls.append((question, gost_number))
        return SelectionResult(
            terms=[terms[1]],
            model="fake-selector",
            provider="fake",
            criteria="system-level",
        )


def build_service():
    service = object.__new__(AskService)
    service.settings = SimpleNamespace()
    service.retriever = Resolver()
    service.term_catalog = TermCatalog(ROWS)
    service.term_selector = Selector()
    return service


def test_inventory_answer_is_deterministic_and_cited():
    service = build_service()
    answer = asyncio.run(
        service._answer_adaptive_plan(
            AdaptivePlan("term_inventory", "ГОСТ Р 71476—2024", "Какие термины?")
        )
    )
    assert answer is not None
    assert answer.model == "deterministic:term_inventory"
    assert "2 термина" in answer.answer
    assert len(answer.citations) == 1


def test_subset_answer_uses_selector_and_citations():
    service = build_service()
    answer = asyncio.run(
        service._answer_adaptive_plan(
            AdaptivePlan(
                "term_subset",
                "ГОСТ Р 71476—2024",
                "Какие термины характеризуют систему?",
            )
        )
    )
    assert answer is not None
    assert answer.model == "fake-selector"
    assert "3.1.4" in answer.answer
    assert "Критерий отбора: system-level" in answer.answer
    assert len(answer.citations) == 1
    assert answer.citations[0].clause == "3.1.4"


def test_ask_routes_inventory_question_without_llm():
    service = build_service()
    result = asyncio.run(
        service.ask(
            "Какие основные термины определены в ГОСТ Р 71476—2024?"
        )
    )
    assert result.answer.model == "deterministic:term_inventory"
    assert result.chunks == []
    assert "2 термина" in result.answer.answer
