from app.ingest.chunk import MAX_CHARS, _clean_cell, _split_long, build_chunks
from app.ingest.parse import Clause, DocMeta, ParsedDocument, Table


def test_short_text_is_not_split():
    assert _split_long("короткий текст") == ["короткий текст"]


def test_long_text_is_split_under_limit():
    text = "Это предложение. " * 500
    parts = _split_long(text)
    assert len(parts) > 1
    assert all(len(part) <= MAX_CHARS for part in parts)


def test_semicolon_list_is_split():
    text = "; ".join([f"аббревиатура номер {i}" for i in range(200)])
    parts = _split_long(text)
    assert all(len(part) <= MAX_CHARS for part in parts)


def test_clean_cell_normalizes_identifier():
    assert _clean_cell("Acc-I -1 р е") == "Acc-I-1"


def test_clean_cell_removes_watermark_letters():
    assert _clean_cell("Р Neural machine translation") == "Neural machine translation"
    assert _clean_cell("Т Е Transformer") == "Transformer"
    assert _clean_cell("покГазателей") == "показателей"
    assert _clean_cell("О К Функциональность оптимизации") == "Функциональность оптимизации"


def test_build_chunks_adds_meta_and_table():
    doc = ParsedDocument(
        meta=DocMeta(
            doc_id="doc",
            filename="doc.pdf",
            doc_type="ГОСТ Р",
            gost_number="ГОСТ Р 1—2024",
            title="Тестовый стандарт",
            valid_from="2025—01—01",
        ),
        clauses=[
            Clause(
                number="1",
                title="Область применения",
                text="Область применения настоящего стандарта.",
                page=5,
                section="1",
                section_title="Область применения",
            )
        ],
        tables=[
            Table(
                page=7,
                index=1,
                rows=[["Идентификатор", "Название"], ["Acc-I-1", "Прецизионность"]],
                number="1",
                title="ПК прецизионности",
            )
        ],
    )
    chunks = build_chunks(doc, "test", "doc.pdf")
    kinds = {chunk.chunk_type for chunk in chunks}
    assert kinds == {"meta", "clause", "table"}
    table = next(chunk for chunk in chunks if chunk.chunk_type == "table")
    assert table.clause == "Таблица 1"
    assert "Acc-I-1" in table.text
