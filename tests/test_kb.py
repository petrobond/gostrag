from pathlib import Path
from types import SimpleNamespace

from app.kb.formatting import format_outline
from app.kb.kb import KnowledgeBase
from app.rag.generator import Answer, Citation
from app.rag.service import AskService
from scripts.build_kb import build_outline


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
        if gost == "ГОСТ Р 71540—2024" and clause == "2":
            return [
                {
                    "text": "2 Нормативные ссылки. В настоящем стандарте использованы ссылки.",
                    "page": 5,
                    "provenance": {"file": "gost-r-71540-2024.pdf"},
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


def test_corpus_links_are_internal_not_external():
    question = "На какие стандарты корпуса ссылается ГОСТ Р 71540—2024?"
    assert not AskService._is_external_links_question(question.lower())

    service = SimpleNamespace(
        kb=kb(),
        chunks=FakeChunks(),
        _is_external_links_question=AskService._is_external_links_question,
    )
    answer = Answer(
        answer="Ответ LLM",
        citations=[Citation(gost="ГОСТ Р 71540—2024", clause="3.10", page=6, valid=True)],
    )
    AskService._append_kb_links(service, answer, question, ["ГОСТ Р 71540—2024"])

    assert "ГОСТ Р 71476—2024" in answer.answer
    assert "27000" not in answer.answer
    assert "57149" not in answer.answer
    assert len(answer.citations) == 1
    assert answer.citations[0].gost == "ГОСТ Р 71540—2024"
    assert answer.citations[0].clause == "2"


def test_external_links_intent_and_deterministic_answer():
    question = "Какие внешние стандарты упоминает ГОСТ Р 71562—2024?"
    assert AskService._is_external_links_question(question.lower())
    assert AskService._is_external_links_question("нормативные ссылки")
    assert not AskService._is_external_links_question(
        "на какой стандарт ссылается ГОСТ Р 71540—2024 в разделе нормативных ссылок"
    )

    service = SimpleNamespace(
        kb=kb(),
        chunks=FakeChunks(),
        _is_external_links_question=AskService._is_external_links_question,
    )
    answer = Answer(
        answer="Ответ LLM",
        citations=[Citation(gost="ГОСТ Р 71562—2024", clause="6.4", page=12, valid=True)],
    )
    AskService._append_kb_links(service, answer, question, ["ГОСТ Р 71562—2024"])

    assert answer.refused is False
    assert "ГОСТ Р 8.673—2009" in answer.answer
    assert "ГОСТ Р 8.820—2013" in answer.answer
    assert "ГОСТ Р 70462.1—2022" in answer.answer
    assert "ГОСТ Р 57700.37—2021" in answer.answer
    assert "ГОСТ Р 71476—2024" not in answer.answer
    assert len(answer.citations) == 1
    assert answer.citations[0].gost == "ГОСТ Р 71562—2024"
    assert answer.citations[0].clause == "2"
    assert answer.citations[0].page == 5


def test_build_outline_deduplicates_chunks_and_skips_meta():
    rows = [
        {
            "chunk_type": "meta",
            "gost_number": "ГОСТ Р 1—2024",
            "doc_id": "doc",
            "clause": "meta",
            "section": "",
            "section_title": "Титульный лист",
            "clause_title": "Сведения о документе",
            "page": 1,
            "chunk_id": "doc#meta",
        },
        {
            "chunk_type": "clause",
            "gost_number": "ГОСТ Р 1—2024",
            "doc_id": "doc",
            "clause": "4",
            "section": "4",
            "section_title": "Модель качества продукта",
            "clause_title": "Модель качества продукта",
            "page": 7,
            "chunk_id": "doc#4",
        },
        {
            "chunk_type": "clause",
            "gost_number": "ГОСТ Р 1—2024",
            "doc_id": "doc",
            "clause": "4.1",
            "section": "4",
            "section_title": "Модель качества продукта",
            "clause_title": "Общие положения",
            "page": 7,
            "chunk_id": "doc#4.1",
        },
        {
            "chunk_type": "clause",
            "gost_number": "ГОСТ Р 1—2024",
            "doc_id": "doc",
            "clause": "4.1",
            "section": "4",
            "section_title": "Модель качества продукта",
            "clause_title": "Общие положения",
            "page": 7,
            "chunk_id": "doc#4.1#p2",
        },
    ]
    outline = build_outline(rows)["ГОСТ Р 1—2024"]
    assert [section["section"] for section in outline["sections"]] == ["4"]
    assert len(outline["sections"][0]["clauses"]) == 2
    assert "Титульный лист" not in format_outline(outline)


def test_outline_72664_matches_pdf_structure():
    outline = kb().outline("ГОСТ Р 72664—2026")
    assert outline is not None
    text = format_outline(outline)
    assert "• 1 Область применения — 1 п." in text
    assert "• 2 Нормативные ссылки — 1 п." in text
    assert "• 3 Термины и определения — 9 п." in text
    assert "• 4 Модель качества продукта — 7 п." in text
    assert "• 5 Модель качества при использовании системы ИИ — 3 п." in text
    assert "• Приложение A Требования к качеству систем и программного обеспечения SQuaRE — 1 п." in text
    assert "• Приложение B Производительность — 1 п." in text
    assert "• Приложение C Сравнение рискориентированного подхода с качествоориентированным подходом и с моделями качества — 3 п." in text
    assert "Без раздела" not in text
    assert "6 Модель" not in text
    assert "0 Титульный лист" not in text
    assert "(раз" not in text


def test_ask_outline_facts_do_not_contain_fake_section_six():
    service = SimpleNamespace(kb=kb())
    answer = Answer(answer="")
    AskService._append_outline_facts(
        service,
        answer,
        "Какие разделы у ГОСТ Р 72664—2026?",
        ["ГОСТ Р 72664—2026"],
    )
    assert "4 — Модель качества продукта" in answer.answer
    assert "5 — Модель качества при использовании системы ИИ" in answer.answer
    assert "6 —" not in answer.answer
