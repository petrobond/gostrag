from pathlib import Path
from types import SimpleNamespace

from app.kb.kb import KnowledgeBase
from app.rag.generator import Answer
from app.rag.service import AskService


class FakeChunks:
    def find(self, gost: str, clause: str) -> list[dict]:
        if gost == "ГОСТ Р 71562—2024" and clause == "2":
            return [
                {
                    "text": "2 Нормативные ссылки. В настоящем стандарте использованы ссылки.",
                    "page": 5,
                    "provenance": {"file": "gost-r-71562-2024.pdf"},
                }
            ]
        return []


def kb() -> KnowledgeBase:
    return KnowledgeBase(Path("data/kb"))


def test_kb_stats():
    stats = kb().stats()
    assert stats["internal_nodes"] == 37
    assert stats["terms"] >= 120
    assert stats["edges"] >= 100


def test_find_term_graph():
    terms = kb().find_term("граф знаний", "ГОСТ Р 71540—2024")
    assert terms
    assert terms[0]["clause"] == "3.7"


def test_outline_has_sections():
    outline = kb().outline("ГОСТ Р 71484.4—2024")
    assert outline is not None
    assert len(outline["sections"]) >= 6


def test_neighbors_and_path():
    graph = kb()
    assert graph.neighbors("ГОСТ Р 71540—2024")["outgoing"]
    path = graph.path("ГОСТ Р 71476—2024", "ГОСТ Р 59898—2021")
    assert path
    assert path[0] == "ГОСТ Р 71476—2024"
    assert path[-1] == "ГОСТ Р 59898—2021"


def test_expand_query_aliases():
    expansion = kb().expand_query("Что такое ИИ?")
    assert any("интеллект" in item.lower() for item in expansion)


def test_find_gost_normalization():
    graph = kb()
    assert graph.find_gost("гост р 71540-2024") == "ГОСТ Р 71540—2024"


def test_external_neighbors_only_external():
    graph = kb()
    edges = graph.external_neighbors("ГОСТ Р 71562—2024")
    assert [edge["target"] for edge in edges] == [
        "ГОСТ Р 8.673—2009",
        "ГОСТ Р 8.820—2013",
        "ГОСТ Р 70462.1—2022",
        "ГОСТ Р 57700.37—2021",
    ]
    assert all(not edge["internal"] for edge in edges)


def test_external_links_intent_and_deterministic_answer():
    question = "Какие внешние стандарты упоминает ГОСТ Р 71562—2024?"
    assert AskService._is_external_links_question(question.lower())
    assert AskService._is_external_links_question("нормативные ссылки")

    service = SimpleNamespace(
        kb=kb(),
        chunks=FakeChunks(),
        _is_external_links_question=AskService._is_external_links_question,
    )
    answer = Answer(answer="Ответ LLM")
    AskService._append_kb_links(service, answer, question, ["ГОСТ Р 71562—2024"])

    assert answer.refused is False
    assert "ГОСТ Р 8.673—2009" in answer.answer
    assert "ГОСТ Р 8.820—2013" in answer.answer
    assert "ГОСТ Р 70462.1—2022" in answer.answer
    assert "ГОСТ Р 57700.37—2021" in answer.answer
    assert "ГОСТ Р 71476—2024" not in answer.answer
    assert answer.citations
    assert answer.citations[0].gost == "ГОСТ Р 71562—2024"
    assert answer.citations[0].clause == "2"
    assert answer.citations[0].page == 5
