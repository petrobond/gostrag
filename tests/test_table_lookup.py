import json

from app.rag.chunk_store import ChunkStore
from app.rag.retriever import RetrievedChunk
from app.rag.service import AskService


def make_row(chunk_id: str, table_number: str, row_start: int, row_end: int, text: str) -> dict:
    return {
        "chunk_id": chunk_id,
        "doc_id": "doc",
        "gost_number": "ПНСТ 844—2023",
        "doc_type": "ПНСТ",
        "iso_analog": "",
        "section": "",
        "section_title": "Сценарии",
        "clause": f"Таблица {table_number}",
        "clause_title": "Сценарии",
        "page": 8,
        "text": text,
        "text_hash": f"sha256:{chunk_id}",
        "corpus_version": "test",
        "provenance": {"file": "doc.pdf"},
        "chunk_type": "table",
        "table_number": table_number,
        "table_id": "doc#t8-3" if table_number == "6.3" else "doc#t7-1",
        "table_caption": "Сценарии",
        "row_start": row_start,
        "row_end": row_end,
        "row_count": 4 if table_number == "6.3" else 1,
        "header": "Сценарий | Модель",
        "part": 1 if row_start == 1 else 2,
        "parts_total": 2 if table_number == "6.3" else 1,
    }


def test_table_lookup_returns_all_parts_in_row_order(tmp_path):
    rows = [
        make_row("doc#t8-3#p2", "6.3", 3, 4, "BERT | Wikipedia"),
        make_row("doc#t8-3", "6.3", 1, 2, "Классификация | ResNet"),
        make_row("doc#t7-1", "6.1", 1, 1, "Экосистема | Интерфейс"),
    ]
    with (tmp_path / "chunks.jsonl").open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    store = ChunkStore(tmp_path)
    found = store.table_chunks("ПНСТ 844—2023", "6.3")
    assert [row["chunk_id"] for row in found] == ["doc#t8-3", "doc#t8-3#p2"]
    assert found[0]["row_start"] == 1
    assert found[1]["row_start"] == 3

    all_tables = store.table_chunks("ПНСТ 844—2023")
    assert len(all_tables) == 3

    assert store.table_chunks("ПНСТ 844—2023", "6.1")[0]["chunk_id"] == "doc#t7-1"


def test_deterministic_table_answer_lists_all_rows():
    chunk = RetrievedChunk(
        chunk_id="doc#t8-3",
        text="Таблица 6.3 — Сценарии. Сценарий | Модель\nA | 1\nB | 2",
        gost_number="ПНСТ 844—2023",
        clause="Таблица 6.3",
        section="",
        section_title="Сценарии",
        page=8,
        score=1.0,
        doc_id="doc",
        clause_title="Сценарии",
        table_number="6.3",
        header="Сценарий | Модель",
    )
    answer = AskService._table_answer("Что приведено в таблице 6.3?", [chunk])
    assert answer is not None
    assert "A | 1" in answer.answer
    assert "B | 2" in answer.answer
    assert answer.citations[0].gost == "ПНСТ 844—2023"
    assert answer.citations[0].clause == "Таблица 6.3"
    assert answer.citations[0].page == 8
    assert answer.model == "deterministic:table"
