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
