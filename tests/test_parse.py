from pathlib import Path

from app.ingest.extract import PageSpans, Span, TableBlock
from app.ingest.parse import _appendix_heading, _is_meaningful_table, parse_document


def _span(
    text: str,
    *,
    block: int,
    line: int = 0,
    size: float = 10.0,
    y: float = 100.0,
) -> Span:
    return Span(
        page=1,
        text=text,
        bbox=(100.0, y, 400.0, y + 14.0),
        color=0x231F20,
        size=size,
        font="Times",
        flags=0,
        block=block,
        line=line,
    )


def test_appendix_heading_uses_status_and_title_lines():
    lines = [
        _span("Приложение B", block=0, size=9, y=124),
        _span("(справочное)", block=1, size=9, y=135),
        _span("Производительность", block=2, size=10, y=185),
        _span("Текст приложения", block=3, size=9, y=210),
    ]
    from app.ingest.clean import Line

    clean_lines = [
        Line(
            page=1,
            block=0,
            line=0,
            text=item.text,
            size=item.size,
            color=item.color,
            bbox=item.bbox,
        )
        for item in lines
    ]
    assert _appendix_heading(clean_lines, 0) == ("B", "Производительность", 3)


def test_watermark_table_is_rejected():
    watermark = TableBlock(
        page=12,
        index=1,
        rows=[["« Ф е д е р а", "", ""], ["", "л ь н о е", ""]],
        bbox=(147.0, 296.0, 474.0, 476.0),
    )
    real = TableBlock(
        page=17,
        index=1,
        rows=[["Структура", "ISO/IEC 25059"], ["1 Раздел", "1 Section"]],
        bbox=(42.0, 288.0, 526.0, 695.0),
    )
    assert not _is_meaningful_table(watermark)
    assert _is_meaningful_table(real)


def test_parse_split_section_numbers_and_appendix(monkeypatch):
    page = PageSpans(
        page=1,
        width=595.0,
        height=842.0,
        spans=[
            _span("1 Область применения", block=0, size=12, y=100),
            _span("Текст области применения", block=1, size=10, y=130),
            _span("4", block=2, size=12, y=278),
            _span(" Модель качества продукта", block=2, size=12, y=278),
            _span("4.1 Общие положения", block=3, size=10, y=300),
            _span("Текст раздела четыре", block=3, line=1, size=10, y=315),
            _span("5", block=4, size=12, y=738),
            _span(" Модель качества при использовании системы ИИ", block=4, size=12, y=738),
            _span("5.1 Общие положения", block=5, size=10, y=761),
            _span("Текст раздела пять", block=5, line=1, size=10, y=775),
            _span("Приложение B", block=6, size=9, y=124),
            _span("(справочное)", block=7, size=9, y=135),
            _span("Производительность", block=8, size=10, y=185),
            _span("Текст приложения B", block=9, size=9, y=210),
        ],
    )
    monkeypatch.setattr("app.ingest.parse.extract_pdf", lambda path: [page])
    monkeypatch.setattr("app.ingest.parse.extract_tables", lambda path: [])

    parsed = parse_document(Path("synthetic.pdf"))
    clauses = {item.number: item for item in parsed.clauses}
    assert clauses["4"].section_title == "Модель качества продукта"
    assert clauses["5"].section_title == "Модель качества при использовании системы ИИ"
    assert clauses["Приложение B"].section_title == "Производительность"
    assert clauses["4.1"].section == "4"
    assert clauses["5.1"].section == "5"
