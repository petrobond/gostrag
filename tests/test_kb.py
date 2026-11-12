from pathlib import Path

from app.kb.kb import KnowledgeBase


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
