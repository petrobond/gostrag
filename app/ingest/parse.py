from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from app.ingest.clean import Line, clean_pages, pages_to_lines
from app.ingest.extract import TableBlock, extract_pdf, extract_tables

CLAUSE_RE = re.compile(r"^(\d+(?:\.\d+){1,4})\s+(.+)$")
SECTION_RE = re.compile(r"^(\d{1,2})\s+([А-ЯЁ][^.]{2,90})$")
APPENDIX_RE = re.compile(r"^Приложение\s+([А-ЯA-ZЁ]{1,2})\b(.*)$")
APPENDIX_STATUS_RE = re.compile(r"^\((?:справочное|обязательное)\)\s*", re.IGNORECASE)
APPENDIX_CLAUSE_RE = re.compile(r"^([A-ZА-ЯЁ]\.\d+(?:\.\d+)*)\s+(.+)$")
TOC_RE = re.compile(r"\.\s*\.\s*\.")
PAGE_NUM_RE = re.compile(r"^\d{1,4}$")
PENDING_CLAUSE_RE = re.compile(r"^(\d+(?:\.\d+){1,4})$")
HEADER_RE = re.compile(r"^(ГОСТ\s*Р|ПНСТ)\s*\d+[—-]\d{4}$")
GOST_NUMBER_RE = re.compile(r"(ГОСТ\s*Р|ПНСТ)\s*(\d+(?:\.\d+)?)[—–-](\d{4})")
ISO_RE = re.compile(r"\((ИСО/МЭК|ISO/IEC)\s*([^)]+)\)")
VALID_FROM_RE = re.compile(r"Дата введения\s*[—–-]\s*(\d{4}[—–-]\d{2}[—–-]\d{2})")
TABLE_CAPTION_RE = re.compile(r"^Таблица\s+([А-ЯA-Z]?\.?\s?\d+(?:\.\d+)?)\s*[—–-]?\s*(.*)$")
TABLE_CONT_RE = re.compile(
    r"^(?:Окончание|Продолжение)\s+таблицы\s+([А-ЯA-Z]?\.?\s?\d+(?:\.\d+)?)"
    r"\s*[—–-]?\s*(.*)$"
)
TABLE_HINT_RE = re.compile(r"Таблица\s+[А-ЯA-Z]?\.?\s?\d", re.IGNORECASE)


@dataclass(slots=True)
class DocMeta:
    doc_id: str
    filename: str
    doc_type: str = ""
    gost_number: str = ""
    title: str = ""
    iso_analog: str = ""
    valid_from: str = ""
    pages: int = 0


@dataclass(slots=True)
class Clause:
    number: str
    title: str
    text: str
    page: int
    section: str = ""
    section_title: str = ""
    appendix: str = ""


@dataclass(slots=True)
class Table:
    page: int
    index: int
    rows: list[list[str]]
    number: str = ""
    title: str = ""
    continuation: bool = False


@dataclass(slots=True)
class ParsedDocument:
    meta: DocMeta
    clauses: list[Clause] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)


def _is_toc_line(text: str) -> bool:
    return bool(TOC_RE.search(text))


def _is_header(text: str) -> bool:
    return bool(HEADER_RE.match(text.strip()))


def _is_page_number(text: str) -> bool:
    return bool(PAGE_NUM_RE.match(text.strip()))


def _join(acc: str, line: str) -> str:
    if not acc:
        return line
    if acc.endswith(("\u00ad", "-")) and line[:1].islower():
        return acc[:-1] + line
    return f"{acc} {line}"


def _is_meaningful_table(block: TableBlock) -> bool:
    """Reject watermark/logo regions that pdfplumber sometimes treats as tables."""
    if not block.rows:
        return False
    width = max((len(row) for row in block.rows), default=0)
    if width < 2:
        return False
    meaningful_rows = sum(
        1 for row in block.rows if sum(bool(cell.strip()) for cell in row) >= 2
    )
    return meaningful_rows >= 2


def _inside_table(
    line: Line, table_boxes: list[tuple[int, tuple[float, float, float, float]]]
) -> bool:
    if not table_boxes:
        return False
    x = (line.bbox[0] + line.bbox[2]) / 2
    y = (line.bbox[1] + line.bbox[3]) / 2
    return any(
        page == line.page and box[0] <= x <= box[2] and box[1] <= y <= box[3]
        for page, box in table_boxes
    )


def _appendix_heading(lines: list[Line], idx: int) -> tuple[str, str, int] | None:
    """Parse a multi-line appendix heading.

    Rosstandart PDFs put ``Приложение B``, ``(справочное)`` and the title on
    separate lines.  Returning the next unconsumed line index lets the caller
    skip the status/title lines instead of appending them to the first clause.
    """
    line = lines[idx]
    if line.bbox[1] > 220:
        return None
    match = APPENDIX_RE.match(line.text.strip())
    if not match:
        return None
    appendix = match.group(1)
    title = APPENDIX_STATUS_RE.sub("", match.group(2).strip()).strip()
    next_idx = idx + 1
    if not title:
        while (
            next_idx < len(lines)
            and lines[next_idx].page == line.page
            and APPENDIX_STATUS_RE.match(lines[next_idx].text.strip())
        ):
            next_idx += 1
        parts: list[str] = []
        while next_idx < len(lines) and lines[next_idx].page == line.page and len(parts) < 2:
            candidate = lines[next_idx].text.strip()
            if not candidate:
                break
            if APPENDIX_STATUS_RE.match(candidate):
                next_idx += 1
                continue
            if lines[next_idx].size < 9.5:
                break
            if APPENDIX_CLAUSE_RE.match(candidate) or re.match(
                r"^(?:Таблица|Рисунок)\b", candidate
            ):
                break
            parts.append(candidate)
            next_idx += 1
        title = " ".join(parts).strip()
    return appendix, title, next_idx


def _extract_meta(path: Path, lines: list[Line]) -> DocMeta:
    meta = DocMeta(
        doc_id=path.stem,
        filename=path.name,
        pages=max((line.page for line in lines), default=0),
    )
    title_parts: list[str] = []
    for line in lines:
        text = line.text.strip()
        if not meta.gost_number:
            m = GOST_NUMBER_RE.search(text)
            if m:
                meta.doc_type = m.group(1).replace("ГОСТР", "ГОСТ Р")
                meta.gost_number = f"{m.group(1)} {m.group(2)}—{m.group(3)}"
        if not meta.iso_analog:
            m = ISO_RE.search(text)
            if m:
                meta.iso_analog = f"{m.group(1)} {m.group(2).strip()}"
        if not meta.valid_from:
            m = VALID_FROM_RE.search(text)
            if m:
                meta.valid_from = m.group(1)
        if line.page <= 2 and line.size >= 17 and not _is_page_number(text):
            if GOST_NUMBER_RE.search(text) or "ИСО/МЭК" in text or "ISO/IEC" in text:
                continue
            if text.startswith(("ГОСТ Р", "ГОСТР", "ПНСТ", "Н А Ц", "С Т А", "Р О С", "Ф Е Д")):
                continue
            if re.fullmatch(r"\d{4}\)?", text) or re.fullmatch(r"\d+[—–-]", text):
                continue
            if len(text) > 3:
                title_parts.append(text)
    meta.title = " ".join(title_parts[:6]).strip()
    if not meta.doc_type:
        meta.doc_type = "ПНСТ" if "pnst" in path.stem.lower() else "ГОСТ Р"
    return meta


def _parse_caption_text(text: str) -> tuple[str, str, bool] | None:
    continuation = TABLE_CONT_RE.match(text)
    if continuation:
        return (
            continuation.group(1).replace(" ", ""),
            continuation.group(2).strip(),
            True,
        )
    caption = TABLE_CAPTION_RE.match(text)
    if caption:
        return (caption.group(1).replace(" ", ""), caption.group(2).strip(), False)
    return None


def _table_caption(lines: list[Line], block: TableBlock) -> tuple[str, str, bool]:
    """Bind a caption to the table by bbox, not by page distance.

    pdfplumber gives table bboxes in PDF points.  The caption is the nearest
    caption line above the table (same page) or at the bottom of the previous
    page.  Lines above the caption are never included, so a paragraph before
    the table cannot become part of its title.
    """
    if block.bbox is None:
        return ("", "", False)

    top = block.bbox[1]
    above = [
        line
        for line in lines
        if line.page == block.page
        and line.bbox[3] <= top - 1
        and top - line.bbox[3] <= 60
    ]
    above.sort(key=lambda line: (line.bbox[1], line.bbox[0]))
    for idx in range(len(above) - 1, -1, -1):
        if _parse_caption_text(above[idx].text.strip()):
            text = " ".join(line.text.strip() for line in above[idx:])
            parsed = _parse_caption_text(text)
            if parsed:
                return parsed

    previous = [
        line
        for line in lines
        if line.page == block.page - 1 and line.bbox[1] > 700
    ]
    previous.sort(key=lambda line: (line.bbox[1], line.bbox[0]))
    for idx in range(len(previous) - 1, -1, -1):
        if _parse_caption_text(previous[idx].text.strip()):
            text = " ".join(line.text.strip() for line in previous[idx:])
            parsed = _parse_caption_text(text)
            if parsed:
                return parsed
    return ("", "", False)


def parse_document(pdf_path: Path) -> ParsedDocument:
    raw_pages = extract_pdf(pdf_path)
    lines = pages_to_lines(clean_pages(raw_pages))
    meta = _extract_meta(pdf_path, lines)
    tables: list[Table] = []
    table_blocks = [
        block for block in extract_tables(pdf_path) if _is_meaningful_table(block)
    ]
    table_boxes = [
        (block.page, block.bbox) for block in table_blocks if block.bbox is not None
    ]
    for block in table_blocks:
        number, title, continuation = _table_caption(lines, block)
        tables.append(
            Table(
                page=block.page,
                index=block.index,
                rows=block.rows,
                number=number,
                title=title,
                continuation=continuation,
            )
        )
    for table in tables:
        if table.continuation and not table.title:
            previous = next(
                (
                    item
                    for item in tables
                    if item.number == table.number and item.title and item is not table
                ),
                None,
            )
            if previous:
                table.title = previous.title

    clauses: list[Clause] = []
    current: Clause | None = None
    section = ""
    section_title = ""
    appendix = ""
    started = False
    pending_number = ""
    skip_until = -1

    def flush() -> None:
        nonlocal current
        if current and current.text.strip():
            text = current.text.replace("\u00ad", "")
            text = re.sub(
                r"\b[А-ЯЁA-Zа-яёa-z](?:\s[А-ЯЁA-Zа-яёa-z]){2,}\b",
                lambda m: m.group(0).replace(" ", ""),
                text,
            )
            current.text = re.sub(r"\s+", " ", text).strip()
            current.title = current.title.replace("\u00ad", "")
            clauses.append(current)
        current = None

    for idx, line in enumerate(lines):
        if idx <= skip_until:
            continue
        text = line.text.strip()
        if not text or _is_toc_line(text) or _is_header(text) or _is_page_number(text):
            continue
        if _inside_table(line, table_boxes) and APPENDIX_CLAUSE_RE.match(text):
            continue

        appendix_heading = _appendix_heading(lines, idx)
        if appendix_heading and started:
            appendix, section_title, next_idx = appendix_heading
            flush()
            section = f"Приложение {appendix}"
            current = Clause(
                number=section,
                title=section_title,
                text=section_title,
                page=line.page,
                section=section,
                section_title=section_title,
                appendix=appendix,
            )
            skip_until = next_idx - 1
            continue

        m_sec = SECTION_RE.match(text)
        if m_sec and line.size >= 11:
            flush()
            appendix = ""
            section = m_sec.group(1)
            section_title = m_sec.group(2).strip()
            if section == "1" and "область применения" in section_title.lower():
                started = True
            if started:
                current = Clause(
                    number=section,
                    title=section_title,
                    text=section_title,
                    page=line.page,
                    section=section,
                    section_title=section_title,
                    appendix=appendix,
                )
            continue

        m_acl = APPENDIX_CLAUSE_RE.match(text)
        if m_acl and started:
            flush()
            pending_number = ""
            current = Clause(
                number=m_acl.group(1),
                title=m_acl.group(2).strip()[:180],
                text=m_acl.group(2).strip(),
                page=line.page,
                section=section,
                section_title=section_title,
                appendix=appendix,
            )
            continue

        m_cl = CLAUSE_RE.match(text)
        if m_cl and started:
            flush()
            pending_number = ""
            current = Clause(
                number=m_cl.group(1),
                title=m_cl.group(2).strip()[:180],
                text=m_cl.group(2).strip(),
                page=line.page,
                section=section,
                section_title=section_title,
                appendix=appendix,
            )
            continue

        m_pending = PENDING_CLAUSE_RE.match(text)
        if m_pending and started:
            flush()
            pending_number = m_pending.group(1)
            continue

        if started and pending_number and not current:
            current = Clause(
                number=pending_number,
                title=text[:180],
                text=text,
                page=line.page,
                section=section,
                section_title=section_title,
                appendix=appendix,
            )
            pending_number = ""
            continue

        if started and current:
            current.text = _join(current.text, text)

    flush()
    return ParsedDocument(meta=meta, clauses=clauses, tables=tables)
