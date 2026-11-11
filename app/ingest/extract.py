from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pymupdf as fitz


@dataclass(slots=True)
class Span:
    """A single text span with layout attributes."""

    page: int
    text: str
    bbox: tuple[float, float, float, float]
    color: int
    size: float
    font: str
    flags: int
    block: int = 0
    line: int = 0


@dataclass(slots=True)
class PageSpans:
    page: int
    width: float
    height: float
    spans: list[Span] = field(default_factory=list)


def rgb_of(color: int) -> tuple[int, int, int]:
    """Convert PyMuPDF integer color to RGB tuple."""
    return ((color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF)


def is_grayish(color: int, tolerance: int = 6) -> bool:
    r, g, b = rgb_of(color)
    return max(r, g, b) - min(r, g, b) <= tolerance


def extract_pdf(pdf_path: Path) -> list[PageSpans]:
    """Extract spans page by page, preserving color/size/coordinates."""
    doc = fitz.open(pdf_path)
    pages: list[PageSpans] = []
    try:
        for page_no, page in enumerate(doc, start=1):
            data = page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)
            result = PageSpans(page=page_no, width=page.rect.width, height=page.rect.height)
            for block_idx, block in enumerate(data.get("blocks", [])):
                if block.get("type") != 0:
                    continue
                for line_idx, line in enumerate(block.get("lines", [])):
                    for span in line.get("spans", []):
                        text = span.get("text", "")
                        if not text.strip():
                            continue
                        result.spans.append(
                            Span(
                                page=page_no,
                                text=text,
                                bbox=tuple(span.get("bbox", (0, 0, 0, 0))),
                                color=int(span.get("color", 0)),
                                size=float(span.get("size", 0)),
                                font=str(span.get("font", "")),
                                flags=int(span.get("flags", 0)),
                                block=block_idx,
                                line=line_idx,
                            )
                        )
            pages.append(result)
    finally:
        doc.close()
    return pages


def extract_text_layout(pdf_path: Path) -> str:
    """Plain layout text extraction (fallback / comparison)."""
    doc = fitz.open(pdf_path)
    try:
        return "\n".join(page.get_text("text") for page in doc)
    finally:
        doc.close()


@dataclass(slots=True)
class TableBlock:
    """A table detected on a page; rows are lists of flattened cell strings."""

    page: int
    index: int
    rows: list[list[str]]


def extract_tables(pdf_path: Path, pages_hint: set[int] | None = None) -> list[TableBlock]:
    """Extract tables page by page: pdfplumber first, PyMuPDF fallback for missed pages."""
    import pdfplumber

    blocks: list[TableBlock] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            if pages_hint is not None and page_no not in pages_hint:
                continue
            for idx, table in enumerate(page.extract_tables() or [], start=1):
                rows = [
                    [(cell or "").replace("\n", " ").strip() for cell in row]
                    for row in table
                    if row and any((cell or "").strip() for cell in row)
                ]
                if len(rows) < 2:
                    continue
                blocks.append(TableBlock(page=page_no, index=idx, rows=rows))
    covered = {block.page for block in blocks}
    missing = (pages_hint - covered) if pages_hint is not None else None
    if missing:
        blocks.extend(_tables_fitz(pdf_path, missing))
    return sorted(blocks, key=lambda block: (block.page, block.index))


def _tables_fitz(pdf_path: Path, pages: set[int]) -> list[TableBlock]:
    """Fallback table extraction via PyMuPDF for pages pdfplumber could not parse."""
    doc = fitz.open(pdf_path)
    blocks: list[TableBlock] = []
    try:
        for page_no in sorted(pages):
            if page_no < 1 or page_no > doc.page_count:
                continue
            for idx, table in enumerate(doc[page_no - 1].find_tables().tables, start=1):
                rows = [
                    [(cell or "").replace("\n", " ").strip() for cell in row]
                    for row in table.extract()
                    if row and any((cell or "").strip() for cell in row)
                ]
                if len(rows) < 2:
                    continue
                blocks.append(TableBlock(page=page_no, index=idx, rows=rows))
    finally:
        doc.close()
    return blocks
