import json
from pathlib import Path
from types import SimpleNamespace

from app.llm.chain import classify
from app.rag.chunk_store import ChunkStore
from app.rag.retriever import Retriever
from app.retrieval.fusion import rrf


def test_rrf_prefers_items_present_in_both_lists():
    fused = rrf([["a", "b", "c"], ["b", "d"]], top_n=3)
    assert fused[0][0] == "b"


def test_rrf_returns_top_n():
    fused = rrf([["a", "b", "c"]], top_n=2)
    assert len(fused) == 2


def test_classify_simple():
    assert classify("Что такое граф знаний?") == "simple"


def test_classify_complex():
    assert classify("Сравни требования к качеству данных в 71484.2 и 72663 и объясни различия") == "complex"


def test_classify_medium():
    question = (
        "Опишите, какие этапы включает процесс управления качеством данных "
        "по ГОСТ Р 71484.4—2024 и как они соотносятся между собой"
    )
    assert classify(question) == "medium"


def make_chunks(tmp_path: Path) -> ChunkStore:
    rows = [
        {
            "chunk_id": "docA#4.1",
            "doc_id": "docA",
            "gost_number": "ГОСТ Р 1—2024",
            "clause": "4.1",
            "clause_title": "Общие положения",
            "section": "4",
            "section_title": "Модель качества",
            "page": 7,
            "text": "Общие положения модели качества систем ИИ",
        },
        {
            "chunk_id": "docA#4.2",
            "doc_id": "docA",
            "gost_number": "ГОСТ Р 1—2024",
            "clause": "4.2",
            "clause_title": "Управляемость",
            "section": "4",
            "section_title": "Модель качества",
            "page": 8,
            "text": "Управляемость системой ИИ со стороны пользователя",
        },
        {
            "chunk_id": "docB#5.1",
            "doc_id": "docB",
            "gost_number": "ПНСТ 2—2023",
            "clause": "5.1",
            "clause_title": "Общие положения",
            "section": "5",
            "section_title": "Модель качества",
            "page": 9,
            "text": "Общие положения модели качества данных",
        },
    ]
    with (tmp_path / "chunks.jsonl").open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return ChunkStore(tmp_path)


def make_retriever(tmp_path: Path) -> Retriever:
    return Retriever(
        settings=None,  # type: ignore[arg-type]
        embedder=None,  # type: ignore[arg-type]
        bm25=None,  # type: ignore[arg-type]
        qdrant=None,  # type: ignore[arg-type]
        chunks=make_chunks(tmp_path),
    )


def test_enumeration_anchor_prefers_dense_then_adds_second(tmp_path):
    retriever = make_retriever(tmp_path)
    bm25_hits = [
        SimpleNamespace(chunk_id="docA#4.2", score=5.0),
        SimpleNamespace(chunk_id="docB#5.1", score=4.5),
    ]
    dense_hits = [
        SimpleNamespace(chunk_id="docA#4.1", score=0.9),
        SimpleNamespace(chunk_id="docB#5.1", score=0.8),
    ]
    anchors = retriever._enumeration_anchors(bm25_hits, [], None, dense_hits)
    assert anchors[0] == ("docA", "4")
    assert ("docB", "5") in anchors


def test_enumeration_anchor_respects_explicit_gost(tmp_path):
    retriever = make_retriever(tmp_path)
    bm25_hits = [SimpleNamespace(chunk_id="docB#5.1", score=9.0)]
    dense_hits = [SimpleNamespace(chunk_id="docA#4.1", score=0.9)]
    anchors = retriever._enumeration_anchors(
        bm25_hits, [], "ГОСТ Р 1—2024", dense_hits
    )
    assert anchors == [("docA", "4")]


def test_group_order_puts_shallow_clauses_first():
    rows = [
        {"clause": "8.2.1.1"},
        {"clause": "8.3.1"},
        {"clause": "8.1"},
        {"clause": "8.3.3"},
    ]
    ordered = Retriever._group_order(rows)
    assert [row["clause"] for row in ordered] == ["8.1", "8.3.1", "8.3.3", "8.2.1.1"]


def make_retrieved(clause: str, title: str):
    from app.rag.retriever import RetrievedChunk

    return RetrievedChunk(
        chunk_id=f"doc#{clause}",
        text="текст",
        gost_number="ГОСТ Р 1—2024",
        clause=clause,
        section="4",
        section_title="Модель качества",
        page=7,
        score=1.0,
        doc_id="doc",
        clause_title=title,
    )


def test_append_enumeration_titles_adds_missing_items():
    from app.rag.service import AskService

    chunks = [
        make_retrieved("4.1", "Общие положения"),
        make_retrieved("4.2", "Управляемость"),
        make_retrieved("4.3", "Функциональная адаптируемость"),
        make_retrieved("4.4", "Робастность"),
    ]
    result = AskService._append_enumeration_titles("Перечислены: управляемость", chunks)
    assert "Полный перечень пунктов" in result
    assert "4.3 — Функциональная адаптируемость" in result


def test_append_enumeration_titles_keeps_complete_answer():
    from app.rag.service import AskService

    chunks = [
        make_retrieved("4.2", "Управляемость"),
        make_retrieved("4.3", "Функциональная адаптируемость"),
        make_retrieved("4.4", "Робастность"),
    ]
    answer = "Управляемость, функциональная адаптируемость, робастность"
    assert AskService._append_enumeration_titles(answer, chunks) == answer
