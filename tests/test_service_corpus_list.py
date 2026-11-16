from types import SimpleNamespace

from app.rag.service import AskService

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


def make_service(documents):
    service = object.__new__(AskService)
    service.settings = SimpleNamespace(corpus_version="test-version")
    service.corpus_documents = documents
    return service


def test_corpus_list_answer_has_all_meta_citations():
    answer = make_service(DOCUMENTS)._corpus_list_answer()
    assert answer is not None
    assert answer.refused is False
    assert answer.model == "deterministic:corpus_list"
    assert answer.provider == "rules"
    assert "В корпусе 2 стандарта (3 документа)" in answer.answer
    assert len(answer.citations) == 2
    assert {citation.clause for citation in answer.citations} == {"meta"}
    assert all(citation.page == 1 for citation in answer.citations)
    assert all(citation.file for citation in answer.citations)


def test_corpus_list_answer_absent_without_manifest():
    assert make_service([])._corpus_list_answer() is None
