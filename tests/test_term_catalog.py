from app.rag.term_catalog import TermCatalog


def _row(gost, clause, title, text, page=1, file="doc.pdf", chunk_type="clause"):
    return {
        "gost_number": gost,
        "clause": clause,
        "clause_title": title,
        "text": text,
        "page": page,
        "chunk_type": chunk_type,
        "provenance": {"file": file},
    }


ROWS = [
    _row("ГОСТ Р 71476—2024", "3.1", "Термины, относящиеся к ИИ", "heading", page=5),
    _row(
        "ГОСТ Р 71476—2024",
        "3.1.1",
        "агент ИИ (AI agent):",
        "агент ИИ (AI agent): Автоматически действующий объект.",
        page=5,
    ),
    _row(
        "ГОСТ Р 71476—2024",
        "3.1.2",
        "компонент ИИ (AI component):",
        "компонент ИИ (AI component): Элемент системы.",
        page=5,
    ),
    _row("ГОСТ Р 71476—2024", "3.2", "Термины о данных", "heading", page=9),
    _row(
        "ГОСТ Р 71476—2024",
        "3.2.1",
        "данные (data):",
        "данные (data): Представление информации.",
        page=9,
    ),
    _row("ГОСТ Р 71476—2024", "4.1", "Не термин", "text", page=20),
]


def test_catalog_groups_terms_and_sections():
    catalog = TermCatalog(ROWS)
    terms = catalog.for_gost("ГОСТ Р 71476—2024")
    assert len(terms) == 3
    assert catalog.sections("ГОСТ Р 71476—2024") == ["3.1", "3.2"]
    assert [term.clause for term in terms] == ["3.1.1", "3.1.2", "3.2.1"]
    assert terms[0].term == "агент ИИ (AI agent)"
    assert terms[0].page == 5


def test_inventory_contains_all_terms_and_section_counts():
    catalog = TermCatalog(ROWS)
    text = catalog.format_inventory("ГОСТ Р 71476—2024")
    assert "раздел 3" in text
    assert "3 термина" in text
    assert "3.1" in text and "(2):" in text
    assert "• 3.1.1 агент ИИ" in text
    assert "• 3.2.1 данные" in text


def test_section_citations_have_page_and_file():
    catalog = TermCatalog(ROWS)
    citations = catalog.section_citations("ГОСТ Р 71476—2024")
    assert [citation.clause for citation in citations] == ["3.1", "3.2"]
    assert all(citation.page > 0 for citation in citations)
    assert all(citation.file == "doc.pdf" for citation in citations)
    assert all(citation.valid for citation in citations)


def test_unknown_gost_has_no_terms():
    catalog = TermCatalog(ROWS)
    assert not catalog.has_gost("ГОСТ Р 99999—2024")
    assert catalog.for_gost("ГОСТ Р 99999—2024") == []
    assert catalog.format_inventory("ГОСТ Р 99999—2024") == ""
