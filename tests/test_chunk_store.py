import json
from pathlib import Path

from app.rag.chunk_store import ChunkStore


def make_corpus(tmp_path: Path) -> ChunkStore:
    rows = [
        {
            "chunk_id": "doc#8.3.4",
            "doc_id": "doc",
            "gost_number": "ГОСТ Р 71540—2024",
            "clause": "8.3.4",
            "section": "8",
            "section_title": "Архитектура",
            "page": 23,
            "text": "Слой платформы инженерии знаний",
        },
        {
            "chunk_id": "doc#8.3.5",
            "doc_id": "doc",
            "gost_number": "ГОСТ Р 71540—2024",
            "clause": "8.3.5",
            "section": "8",
            "section_title": "Архитектура",
            "page": 23,
            "text": "Слой применения инженерии знаний",
        },
        {
            "chunk_id": "doc2#6.2.5.1",
            "doc_id": "doc2",
            "gost_number": "ГОСТ Р 71484.2—2024",
            "clause": "6.2.5.1",
            "section": "6",
            "section_title": "Качество",
            "page": 10,
            "text": "Актуальность данных",
        },
        {
            "chunk_id": "doc2#6.2.5.1#p2",
            "doc_id": "doc2",
            "gost_number": "ГОСТ Р 71484.2—2024",
            "clause": "6.2.5.1",
            "section": "6",
            "section_title": "Качество",
            "page": 10,
            "text": "Связь с дрейфом данных",
        },
    ]
    with (tmp_path / "chunks.jsonl").open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return ChunkStore(tmp_path)


def test_find_fuzzy_exact(tmp_path):
    store = make_corpus(tmp_path)
    found = store.find_fuzzy("ГОСТ Р 71540—2024", "8.3.4")
    assert len(found) == 1
    assert found[0]["clause"] == "8.3.4"


def test_find_fuzzy_prefix(tmp_path):
    store = make_corpus(tmp_path)
    found = store.find_fuzzy("ГОСТ Р 71484.2—2024", "6.2.5")
    assert len(found) == 2
    assert [row["clause"] for row in found] == ["6.2.5.1", "6.2.5.1"]
    assert found[0]["chunk_id"] == "doc2#6.2.5.1"
    assert found[1]["chunk_id"] == "doc2#6.2.5.1#p2"


def test_section_chunks_sorted(tmp_path):
    store = make_corpus(tmp_path)
    rows = store.section_chunks("doc", "8")
    assert [row["clause"] for row in rows] == ["8.3.4", "8.3.5"]


def test_clause_siblings(tmp_path):
    store = make_corpus(tmp_path)
    rows = store.clause_siblings("doc", "8.3.4")
    assert [row["clause"] for row in rows] == ["8.3.4", "8.3.5"]


def test_duplicate_chunk_id_is_merged(tmp_path):
    rows = [
        {
            "chunk_id": "doc#8.2",
            "doc_id": "doc",
            "gost_number": "ГОСТ Р 72663—2026",
            "clause": "8.2",
            "section": "8",
            "section_title": "Показатели качества данных",
            "clause_title": "Показатели качества прецизионности",
            "page": 17,
            "text": "Первый фрагмент таблицы.",
        },
        {
            "chunk_id": "doc#8.2",
            "doc_id": "doc",
            "gost_number": "ГОСТ Р 72663—2026",
            "clause": "8.2",
            "section": "8",
            "section_title": "Показатели качества данных",
            "clause_title": "Показатели качества прецизионности",
            "page": 17,
            "text": "Acc-I-1 Acc-I-2 Acc-I-7",
        },
    ]
    with (tmp_path / "chunks.jsonl").open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    store = ChunkStore(tmp_path)
    merged = store.get("doc#8.2")
    assert merged is not None
    assert "Первый фрагмент" in merged["text"]
    assert "Acc-I-7" in merged["text"]


def test_find_meta_and_table_chunks(tmp_path):
    rows = [
        {
            "chunk_id": "doc#meta",
            "doc_id": "doc",
            "gost_number": "ГОСТ Р 71540—2024",
            "clause": "meta",
            "section": "",
            "section_title": "Титульный лист",
            "page": 1,
            "text": "Дата введения — 2025—01—01",
            "chunk_type": "meta",
        },
        {
            "chunk_id": "doc#t8-1",
            "doc_id": "doc",
            "gost_number": "ГОСТ Р 71540—2024",
            "clause": "Таблица 1",
            "section": "",
            "section_title": "Таблица 1",
            "page": 8,
            "text": "Идентификатор | Название",
            "chunk_type": "table",
        },
        {
            "chunk_id": "pnst#meta",
            "doc_id": "pnst",
            "gost_number": "ПНСТ 836—2023",
            "clause": "meta",
            "section": "",
            "section_title": "Титульный лист",
            "page": 1,
            "text": "ПНСТ 836—2023. Дата введения — 2024—01—01",
            "chunk_type": "meta",
            "doc_type": "ПНСТ",
        },
    ]
    with (tmp_path / "chunks.jsonl").open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    store = ChunkStore(tmp_path)
    assert [row["chunk_id"] for row in store.find_meta("ГОСТ Р 71540—2024")] == ["doc#meta"]
    assert [row["chunk_id"] for row in store.table_chunks("ГОСТ Р 71540—2024")] == ["doc#t8-1"]
    assert {row["chunk_id"] for row in store.meta_by_doc_type()} == {"doc#meta", "pnst#meta"}
