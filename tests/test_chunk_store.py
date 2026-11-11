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
    assert len(found) == 1
    assert found[0]["clause"] == "6.2.5.1"


def test_section_chunks_sorted(tmp_path):
    store = make_corpus(tmp_path)
    rows = store.section_chunks("doc", "8")
    assert [row["clause"] for row in rows] == ["8.3.4", "8.3.5"]
