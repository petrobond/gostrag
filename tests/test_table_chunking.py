from app.ingest.chunk import build_chunks
from app.ingest.clean import Line
from app.ingest.extract import TableBlock
from app.ingest.parse import DocMeta, ParsedDocument, Table, _table_caption


def make_table(page: int, index: int, number: str, title: str, rows: list[list[str]], continuation: bool = False) -> Table:
    return Table(
        page=page,
        index=index,
        rows=rows,
        number=number,
        title=title,
        continuation=continuation,
    )


def test_caption_is_bound_by_bbox_and_skips_paragraph():
    lines = [
        Line(8, 0, 0, "В таблице 6.3 перечислены примеры", 10, 0, (70, 613, 555, 627)),
        Line(8, 0, 1, "Таблица 6.3 — Сценарии", 10, 0, (70, 658, 555, 670)),
        Line(8, 0, 2, "данных и целями", 10, 0, (70, 669, 300, 681)),
    ]
    block = TableBlock(page=8, index=3, rows=[["a", "b"], ["1", "2"]], bbox=(71, 685, 553, 753))
    number, title, continuation = _table_caption(lines, block)
    assert number == "6.3"
    assert title == "Сценарии данных и целями"
    assert continuation is False


def test_caption_recognizes_continuation():
    lines = [
        Line(8, 0, 0, "Окончание таблицы 6.1", 10, 0, (70, 82, 173, 94)),
    ]
    block = TableBlock(page=8, index=1, rows=[["a", "b"], ["1", "2"]], bbox=(71, 99, 553, 338))
    number, title, continuation = _table_caption(lines, block)
    assert number == "6.1"
    assert title == ""
    assert continuation is True


def test_caption_is_not_taken_without_bbox_caption():
    lines = [
        Line(8, 0, 0, "Обычный абзац перед таблицей", 10, 0, (70, 600, 555, 620)),
    ]
    block = TableBlock(page=8, index=1, rows=[["a", "b"], ["1", "2"]], bbox=(71, 700, 553, 750))
    assert _table_caption(lines, block) == ("", "", False)


def test_table_parts_with_same_number_are_grouped_without_mixing():
    doc = ParsedDocument(
        meta=DocMeta(
            doc_id="doc",
            filename="doc.pdf",
            doc_type="ПНСТ",
            gost_number="ПНСТ 844—2023",
            title="Тестовый стандарт",
        ),
        tables=[
            make_table(
                7,
                1,
                "6.1",
                "Система показателей",
                [["Система", "Показатель"], ["Экосистема", "Интерфейс"]],
            ),
            make_table(
                8,
                1,
                "6.1",
                "Система показателей",
                [["Система", "Показатель"], ["Простота", "Отладка"]],
                continuation=True,
            ),
            make_table(
                8,
                2,
                "6.3",
                "Сценарии",
                [["Сценарий", "Модель"], ["Классификация", "ResNet"]],
            ),
            make_table(
                9,
                1,
                "6.3",
                "Сценарии",
                [["Сценарий", "Модель"], ["BERT", "Wikipedia"]],
                continuation=True,
            ),
        ],
    )
    chunks = build_chunks(doc, "test", "doc.pdf")
    table_chunks = [chunk for chunk in chunks if chunk.chunk_type == "table"]
    chunk_63 = next(chunk for chunk in table_chunks if chunk.table_number == "6.3")
    chunk_61 = next(chunk for chunk in table_chunks if chunk.table_number == "6.1")

    assert chunk_63.chunk_id == "doc#t8-2"
    assert chunk_63.row_count == 2
    assert chunk_63.row_start == 1
    assert chunk_63.row_end == 2
    assert "Классификация" in chunk_63.text
    assert "BERT" in chunk_63.text
    assert "Экосистема" not in chunk_63.text

    assert chunk_61.row_count == 2
    assert "Экосистема" in chunk_61.text
    assert "BERT" not in chunk_61.text
