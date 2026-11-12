from types import SimpleNamespace

from app.rag.generator import Answer
from app.rag.retriever import RetrievedChunk
from app.rag.service import AskService


def chunk(text: str) -> SimpleNamespace:
    return SimpleNamespace(text=text)


def retrieved(text: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="doc#8.2",
        text=text,
        gost_number="ГОСТ Р 72663—2026",
        clause="8.2",
        section="8",
        section_title="Показатели качества данных",
        page=17,
        score=1.0,
        doc_id="doc",
        file="gost-r-72663-2026.pdf",
    )


def test_appends_missing_identifiers():
    answer = "Приведены Acc-I-1 и Acc-I-2."
    chunks = [chunk("Acc-I-1 Acc-I-2 Acc-I-3 Acc-I-4")]
    result = AskService._append_enumeration_ids(answer, chunks)
    assert "Полный перечень показателей" in result
    assert "Acc-I-3" in result
    assert "Acc-I-4" in result


def test_does_not_mix_identifier_families():
    answer = "Для полноты приведены Com-I-1 и Com-I-2."
    chunks = [chunk("Com-I-1 Com-I-2 Com-I-3 Acc-I-1 Acc-I-2 Acc-I-3")]
    result = AskService._append_enumeration_ids(answer, chunks)
    assert "Com-I-3" in result
    assert "Acc-I-1" not in result


def test_keeps_answer_when_all_identifiers_present():
    answer = "Acc-I-1, Acc-I-2, Acc-I-3, Acc-I-4"
    chunks = [chunk("Acc-I-1 Acc-I-2 Acc-I-3 Acc-I-4")]
    assert AskService._append_enumeration_ids(answer, chunks) == answer


def test_attaches_fallback_citation():
    answer = Answer(answer="Ответ без цитаты.")
    AskService._attach_fallback_citation(answer, [retrieved("Acc-I-1 ... Acc-I-7")])
    assert len(answer.citations) == 1
    assert answer.citations[0].gost == "ГОСТ Р 72663—2026"
    assert answer.citations[0].page == 17


def test_fallback_citation_skips_refusal():
    answer = Answer(answer="Нет данных.", refused=True)
    AskService._attach_fallback_citation(answer, [retrieved("текст")])
    assert answer.citations == []
