from app.rag.corpus_catalog import (
    build_corpus_standards,
    build_meta_citations,
    format_corpus_standards,
)

DOCUMENTS = [
    {
        "gost_number": "ГОСТ Р 1—2024",
        "title": "Первый стандарт",
        "doc_type": "ГОСТ Р",
        "chunks": 10,
        "filename": "one.pdf",
    },
    {
        "gost_number": "ГОСТ Р 1—2024",
        "title": "Первый стандарт",
        "doc_type": "ГОСТ Р",
        "chunks": 5,
        "filename": "one-extra.pdf",
    },
    {
        "gost_number": "ПНСТ 2—2023",
        "title": "Второй стандарт",
        "doc_type": "ПНСТ",
        "chunks": 3,
        "filename": "two.pdf",
    },
]


def test_grouping_preserves_documents_and_chunks():
    standards = build_corpus_standards(DOCUMENTS)
    assert len(standards) == 2
    first = standards[0]
    assert first.gost_number == "ГОСТ Р 1—2024"
    assert first.documents == 2
    assert first.chunks == 15


def test_format_is_complete_and_pluralized():
    standards = build_corpus_standards(DOCUMENTS)
    text = format_corpus_standards(
        standards, documents_total=3, corpus_version="test-version"
    )
    assert "В корпусе 2 стандарта (3 документа), версия test-version." in text
    assert "ГОСТ Р 1—2024" in text
    assert "ПНСТ 2—2023" in text
    assert "(документов: 2)" in text
    assert "Источник: documents.json корпуса test-version." in text


def test_meta_citations_have_title_page_and_file():
    standards = build_corpus_standards(DOCUMENTS)
    citations = build_meta_citations(standards)
    assert len(citations) == 2
    for citation in citations:
        assert citation.clause == "meta"
        assert citation.page == 1
        assert citation.file
        assert citation.quote
        assert citation.valid is True


def test_empty_manifest_gives_empty_catalog():
    assert build_corpus_standards([]) == []
