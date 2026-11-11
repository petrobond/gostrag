from __future__ import annotations

import re
from dataclasses import dataclass

from app.ingest.extract import PageSpans, Span, rgb_of

# Service stamps repeated on every page of Rosstandart PDFs.
SERVICE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"федеральное агентство\s+по техническому регулированию и метрологии",
        r"фгбу\s*«?институт стандартизации»?",
        r"институт стандартизации",
        r"российский институт стандартизации",
        r"по техническому\s+регулированию",
        r"регулированию и метрологии»?",
    )
)


def normalize_text(text: str) -> str:
    text = re.sub(
        r"\b[А-ЯЁA-Zа-яёa-z](?:\s[А-ЯЁA-Zа-яёa-z]){2,}\b",
        lambda m: m.group(0).replace(" ", ""),
        text.replace("\xa0", " "),
    )
    return re.sub(r"\s+", " ", text).strip()


def luminance(color: int) -> float:
    r, g, b = rgb_of(color)
    return 0.299 * r + 0.587 * g + 0.114 * b


def saturation(color: int) -> int:
    r, g, b = rgb_of(color)
    return max(r, g, b) - min(r, g, b)


def is_background(color: int) -> bool:
    """Light gray / white watermarks and page headers."""
    return luminance(color) > 150 and saturation(color) < 40


def is_red_stamp(color: int) -> bool:
    """Red service stamps used by Rosstandart."""
    r, g, b = rgb_of(color)
    return r > 200 and g < 80 and b < 80


def is_service_text(text: str) -> bool:
    normalized = normalize_text(text)
    if len(normalized) < 3:
        return False
    return any(p.search(normalized) for p in SERVICE_PATTERNS)


def is_noise_text(text: str) -> bool:
    """Single letters and punctuation left after watermark removal."""
    normalized = normalize_text(text)
    if not normalized:
        return True
    if len(normalized) == 1:
        return True
    if len(normalized) <= 3 and normalized.isupper() and normalized.isalpha():
        return True
    return False


def should_drop(span: Span) -> bool:
    if is_background(span.color) or is_red_stamp(span.color):
        return True
    if is_service_text(span.text):
        return True
    return False


@dataclass(slots=True)
class Line:
    page: int
    block: int
    line: int
    text: str
    size: float
    color: int
    bbox: tuple[float, float, float, float]


def clean_pages(pages: list[PageSpans]) -> list[PageSpans]:
    """Remove watermarks, service stamps and noise spans."""
    cleaned: list[PageSpans] = []
    for page in pages:
        kept = [s for s in page.spans if not should_drop(s) and not is_noise_text(s.text)]
        cleaned.append(
            PageSpans(page=page.page, width=page.width, height=page.height, spans=kept)
        )
    return cleaned


def pages_to_lines(pages: list[PageSpans]) -> list[Line]:
    """Group cleaned spans into lines, preserving reading order."""
    lines: list[Line] = []
    for page in pages:
        grouped: dict[tuple[int, int], list[Span]] = {}
        for span in page.spans:
            grouped.setdefault((span.block, span.line), []).append(span)
        for (block, line), spans in sorted(grouped.items()):
            spans.sort(key=lambda s: s.bbox[0])
            text = " ".join(normalize_text(s.text) for s in spans if normalize_text(s.text))
            if not text:
                continue
            sizes = [s.size for s in spans]
            bbox = (
                min(s.bbox[0] for s in spans),
                min(s.bbox[1] for s in spans),
                max(s.bbox[2] for s in spans),
                max(s.bbox[3] for s in spans),
            )
            lines.append(
                Line(
                    page=page.page,
                    block=block,
                    line=line,
                    text=text,
                    size=max(sizes) if sizes else 0.0,
                    color=spans[0].color,
                    bbox=bbox,
                )
            )
    return lines
