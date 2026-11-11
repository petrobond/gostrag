from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass

from app.ingest.parse import ParsedDocument

MAX_CHARS = 1800
MIN_CHARS = 40
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
IDENT_RE = re.compile(r"^[A-Za-zА-Яа-яЁё][^\s]{0,8}\d")
NOISE_LETTER_RE = re.compile(r"(?:^|\s)[а-яёa-z](?=\s|$)")


@dataclass(slots=True)
class Chunk:
    chunk_id: str
    doc_id: str
    gost_number: str
    doc_type: str
    iso_analog: str
    section: str
    section_title: str
    clause: str
    clause_title: str
    page: int
    text: str
    text_hash: str
    corpus_version: str
    provenance: dict
    chunk_type: str = "clause"

    def to_dict(self) -> dict:
        return asdict(self)


def _hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _split_long(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    current = ""
    for sentence in SENTENCE_RE.split(text):
        if len(sentence) > max_chars:
            for chunk in re.split(r"(?<=[;:])\s+", sentence):
                if not current:
                    current = chunk
                elif len(current) + 1 + len(chunk) <= max_chars:
                    current = f"{current} {chunk}"
                else:
                    parts.append(current)
                    current = chunk
            continue
        if not current:
            current = sentence
        elif len(current) + 1 + len(sentence) <= max_chars:
            current = f"{current} {sentence}"
        else:
            parts.append(current)
            current = sentence
    if current:
        parts.append(current)
    result: list[str] = []
    for part in parts:
        if len(part) <= max_chars:
            result.append(part)
            continue
        words = part.split()
        buf = ""
        for word in words:
            if not buf:
                buf = word
            elif len(buf) + 1 + len(word) <= max_chars:
                buf = f"{buf} {word}"
            else:
                result.append(buf)
                buf = word
        if buf:
            result.append(buf)
    return result


def _provenance(filename: str, source_span: str) -> dict:
    return {
        "file": filename,
        "parser": "pymupdf+pdfplumber",
        "parser_version": "2.2",
        "extracted_at": "",
        "source_span": source_span,
        "owner": "corpus-admin",
        "review_status": "approved",
    }


def _meta_chunk(doc: ParsedDocument, corpus_version: str, filename: str) -> Chunk | None:
    """Document-level facts: title, effective date and ISO analog."""
    meta = doc.meta
    bits = [meta.gost_number, meta.title]
    if meta.valid_from:
        bits.append(f"Дата введения — {meta.valid_from}")
    if meta.iso_analog:
        bits.append(f"Соответствует {meta.iso_analog}")
    text = ". ".join(bit.strip(" .") for bit in bits if bit.strip())
    if len(text) < MIN_CHARS:
        return None
    return Chunk(
        chunk_id=f"{meta.doc_id}#meta",
        doc_id=meta.doc_id,
        gost_number=meta.gost_number,
        doc_type=meta.doc_type,
        iso_analog=meta.iso_analog,
        section="",
        section_title="Титульный лист",
        clause="meta",
        clause_title="Сведения о документе",
        page=1,
        text=text,
        text_hash=_hash(text),
        corpus_version=corpus_version,
        provenance=_provenance(filename, f"{meta.doc_id}#meta"),
        chunk_type="meta",
    )


def _clean_cell(value: str) -> str:
    """Drop soft hyphens, join "Acc-I -1" and noise letters inside identifier cells."""
    text = value.replace("\xad", "").replace("\u00ad", "")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"(?<=[A-Za-zА-Яа-я])\s*-\s*(?=\d)", "-", text)
    if IDENT_RE.match(text):
        text = NOISE_LETTER_RE.sub(" ", text)
        text = re.sub(r"\s+", " ", text).strip()
    return text


def _table_chunks(doc: ParsedDocument, corpus_version: str, filename: str) -> list[Chunk]:
    """One chunk per table part: caption plus pipe-separated rows."""
    chunks: list[Chunk] = []
    for table in doc.tables:
        rows = [
            [_clean_cell(cell) for cell in row]
            for row in table.rows
            if row and any((cell or "").strip() for cell in row)
        ]
        if len(rows) < 2:
            continue
        clause = f"Таблица {table.number}" if table.number else f"Таблица (с. {table.page})"
        header = " | ".join(rows[0])
        prefix = f"{clause} — {table.title}. " if table.title else f"{clause}. "
        parts: list[str] = []
        current = prefix + header
        for row in rows[1:]:
            line = " | ".join(row)
            if len(current) + 1 + len(line) > MAX_CHARS:
                parts.append(current)
                current = f"{clause}. {header}\n{line}"
            else:
                current = f"{current}\n{line}"
        parts.append(current)
        for idx, part in enumerate(parts, start=1):
            if len(part) < MIN_CHARS:
                continue
            suffix = f"#p{idx}" if idx > 1 else ""
            chunks.append(
                Chunk(
                    chunk_id=f"{doc.meta.doc_id}#t{table.page}-{table.index}{suffix}",
                    doc_id=doc.meta.doc_id,
                    gost_number=doc.meta.gost_number,
                    doc_type=doc.meta.doc_type,
                    iso_analog=doc.meta.iso_analog,
                    section="",
                    section_title=table.title or f"Таблица (с. {table.page})",
                    clause=clause,
                    clause_title=table.title[:180],
                    page=table.page,
                    text=part,
                    text_hash=_hash(part),
                    corpus_version=corpus_version,
                    provenance=_provenance(filename, f"{doc.meta.doc_id}#t{table.page}-{table.index}"),
                    chunk_type="table",
                )
            )
    return chunks


def build_chunks(doc: ParsedDocument, corpus_version: str, filename: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    meta_chunk = _meta_chunk(doc, corpus_version, filename)
    if meta_chunk is not None:
        chunks.append(meta_chunk)
    for clause in doc.clauses:
        text = clause.text.strip()
        if len(text) < MIN_CHARS:
            continue
        for idx, part in enumerate(_split_long(text), start=1):
            suffix = f"#p{idx}" if idx > 1 else ""
            chunk_id = f"{doc.meta.doc_id}#{clause.number}{suffix}"
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    doc_id=doc.meta.doc_id,
                    gost_number=doc.meta.gost_number,
                    doc_type=doc.meta.doc_type,
                    iso_analog=doc.meta.iso_analog,
                    section=clause.section,
                    section_title=clause.section_title,
                    clause=clause.number,
                    clause_title=clause.title,
                    page=clause.page,
                    text=part,
                    text_hash=_hash(part),
                    corpus_version=corpus_version,
                    provenance=_provenance(filename, f"{doc.meta.doc_id}#{clause.number}"),
                )
            )
    chunks.extend(_table_chunks(doc, corpus_version, filename))
    return chunks


def chunk_stats(chunks: list[Chunk]) -> dict:
    if not chunks:
        return {"count": 0}
    lengths = [len(c.text) for c in chunks]
    return {
        "count": len(chunks),
        "min_chars": min(lengths),
        "max_chars": max(lengths),
        "avg_chars": round(sum(lengths) / len(lengths), 1),
        "unique_docs": len({c.doc_id for c in chunks}),
    }
