from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass

from app.ingest.parse import Clause, ParsedDocument

MAX_CHARS = 1800
MIN_CHARS = 40
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


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


def build_chunks(doc: ParsedDocument, corpus_version: str, filename: str) -> list[Chunk]:
    chunks: list[Chunk] = []
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
                    provenance={
                        "file": filename,
                        "parser": "pymupdf",
                        "parser_version": "2.1",
                        "extracted_at": "",
                        "source_span": f"{doc.meta.doc_id}#{clause.number}",
                        "owner": "corpus-admin",
                        "review_status": "approved",
                    },
                )
            )
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
