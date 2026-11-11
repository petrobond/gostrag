from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from app.ingest.clean import Line, clean_pages, pages_to_lines
from app.ingest.extract import extract_pdf

CLAUSE_RE = re.compile(r"^(\d+(?:\.\d+){1,4})\s+(.+)$")
SECTION_RE = re.compile(r"^(\d{1,2})\s+([А-ЯЁ][^.]{2,90})$")
APPENDIX_RE = re.compile(r"^Приложение\s+([А-ЯA-Z])\b(.*)$")
TOC_RE = re.compile(r"\.\s*\.\s*\.")
PAGE_NUM_RE = re.compile(r"^\d{1,4}$")
PENDING_CLAUSE_RE = re.compile(r"^(\d+(?:\.\d+){1,4})$")
HEADER_RE = re.compile(r"^(ГОСТ\s*Р|ПНСТ)\s*\d+[—-]\d{4}$")
GOST_NUMBER_RE = re.compile(r"(ГОСТ\s*Р|ПНСТ)\s*(\d+(?:\.\d+)?)[—–-](\d{4})")
ISO_RE = re.compile(r"\((ИСО/МЭК|ISO/IEC)\s*([^)]+)\)")
VALID_FROM_RE = re.compile(r"Дата введения\s*[—–-]\s*(\d{4}[—–-]\d{2}[—–-]\d{2})")


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
class ParsedDocument:
    meta: DocMeta
    clauses: list[Clause] = field(default_factory=list)


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


def _extract_meta(path: Path, lines: list[Line]) -> DocMeta:
    meta = DocMeta(doc_id=path.stem, filename=path.name, pages=max((l.page for l in lines), default=0))
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


def parse_document(pdf_path: Path) -> ParsedDocument:
    raw_pages = extract_pdf(pdf_path)
    lines = pages_to_lines(clean_pages(raw_pages))
    meta = _extract_meta(pdf_path, lines)

    clauses: list[Clause] = []
    current: Clause | None = None
    section = ""
    section_title = ""
    appendix = ""
    started = False
    pending_number = ""

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

    for line in lines:
        text = line.text.strip()
        if not text or _is_toc_line(text) or _is_header(text) or _is_page_number(text):
            continue

        m_app = APPENDIX_RE.match(text)
        if m_app:
            flush()
            appendix = m_app.group(1)
            section = f"Приложение {appendix}"
            section_title = m_app.group(2).strip()
            continue

        m_sec = SECTION_RE.match(text)
        if m_sec:
            flush()
            section = m_sec.group(1)
            section_title = m_sec.group(2).strip()
            if section == "1" and "область применения" in section_title.lower():
                started = True
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
    return ParsedDocument(meta=meta, clauses=clauses)
