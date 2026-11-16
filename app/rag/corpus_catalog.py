"""Deterministic catalog of corpus standards for inventory questions."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from app.rag.generator import Citation

TYPE_ORDER = {"ГОСТ Р": 0, "ПНСТ": 1}
OTHER_TYPE = "Прочее"


@dataclass(frozen=True, slots=True)
class CorpusStandard:
    gost_number: str
    title: str
    doc_type: str
    documents: int
    chunks: int
    filename: str


def _norm(value: str) -> str:
    return re.sub(r"[\s—–-]+", "", (value or "")).lower()


def _natural(value: str) -> tuple[int, ...]:
    return tuple(int(item) for item in re.findall(r"\d+", value or ""))


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _plural(count: int, one: str, few: str, many: str) -> str:
    tail = count % 100
    if 11 <= tail <= 14:
        return many
    last = count % 10
    if last == 1:
        return one
    if 2 <= last <= 4:
        return few
    return many


def build_corpus_standards(documents: Iterable[Mapping[str, Any]]) -> list[CorpusStandard]:
    """Group document-manifest rows into unique standards.

    A standard may have several documents (e.g. two files for 71540); the
    number of documents and total chunks are preserved, while the designation
    is listed once.
    """
    grouped: dict[str, dict[str, Any]] = {}
    for doc in documents:
        gost = str(doc.get("gost_number") or doc.get("doc_id") or "").strip()
        if not gost:
            continue
        key = _norm(gost)
        title = str(doc.get("title") or "").strip()
        doc_type = str(doc.get("doc_type") or "").strip() or OTHER_TYPE
        filename = str(doc.get("filename") or "").strip()
        chunks = _as_int(doc.get("chunks"))
        entry = grouped.get(key)
        if entry is None:
            grouped[key] = {
                "gost_number": gost,
                "title": title or filename,
                "doc_type": doc_type,
                "documents": 1,
                "chunks": chunks,
                "filename": filename,
            }
            continue
        entry["documents"] += 1
        entry["chunks"] += chunks
        if not entry["title"] and (title or filename):
            entry["title"] = title or filename
        if not entry["filename"] and filename:
            entry["filename"] = filename
        if entry["doc_type"] == OTHER_TYPE and doc_type != OTHER_TYPE:
            entry["doc_type"] = doc_type

    return sorted(
        (CorpusStandard(**entry) for entry in grouped.values()),
        key=lambda item: (
            TYPE_ORDER.get(item.doc_type, 2),
            _natural(item.gost_number),
            item.gost_number.lower(),
        ),
    )


def format_corpus_standards(
    standards: list[CorpusStandard],
    *,
    documents_total: int,
    corpus_version: str,
) -> str:
    """Render the complete inventory; no truncation of the standards list."""
    lines = [
        f"В корпусе {len(standards)} "
        f"{_plural(len(standards), 'стандарт', 'стандарта', 'стандартов')} "
        f"({documents_total} "
        f"{_plural(documents_total, 'документ', 'документа', 'документов')}), "
        f"версия {corpus_version}."
    ]
    for type_name in ("ГОСТ Р", "ПНСТ", OTHER_TYPE):
        group = [item for item in standards if item.doc_type == type_name]
        if not group:
            continue
        lines.extend(["", f"{type_name} ({len(group)}):"])
        for item in group:
            suffix = f" (документов: {item.documents})" if item.documents > 1 else ""
            lines.append(f"• {item.gost_number} — {item.title[:160]}{suffix}")
    lines.extend(["", f"Источник: documents.json корпуса {corpus_version}."])
    return "\n".join(lines)


def build_meta_citations(standards: list[CorpusStandard]) -> list[Citation]:
    """One meta citation per standard: title page, file and quote from manifest."""
    return [
        Citation(
            gost=item.gost_number,
            clause="meta",
            page=1,
            quote=(item.title or item.gost_number)[:200],
            file=item.filename,
            valid=True,
            page_valid=True,
            quote_valid=True,
        )
        for item in standards
    ]
