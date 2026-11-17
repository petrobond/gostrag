"""Read-only data adapters for web tools (/tools/*)."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.kb.kb import KnowledgeBase
from app.rag.chunk_store import ChunkStore
from app.rag.corpus_catalog import build_corpus_standards
from app.rag.term_catalog import TermCatalog


def _norm_gost(value: str) -> str:
    return re.sub(r"[\s—–-]+", "", (value or "")).lower()


class ToolService:
    """Small read-only facade over documents, KB and the term catalog."""

    def __init__(self, settings, service=None, s3=None) -> None:
        self.settings = settings
        self.service = service
        self.s3 = s3
        self.kb = getattr(service, "kb", None) if service is not None else None
        if self.kb is None:
            try:
                self.kb = KnowledgeBase()
            except (FileNotFoundError, ValueError):
                self.kb = None
        self.term_catalog = (
            getattr(service, "term_catalog", None) if service is not None else None
        )
        if self.term_catalog is None:
            corpus = self._corpus_dir()
            if (corpus / "chunks.jsonl").exists():
                try:
                    self.term_catalog = TermCatalog(ChunkStore(corpus).by_id.values())
                except (OSError, ValueError):
                    self.term_catalog = None

    def _corpus_dir(self) -> Path:
        configured = Path(self.settings.data_corpus_dir)
        if (configured / "chunks.jsonl").exists() or (configured / "documents.json").exists():
            return configured
        fallback = Path("data/corpus")
        return fallback if fallback.exists() else configured

    def _documents(self) -> list[dict]:
        path = self._corpus_dir() / "documents.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    def _pdf(self, filename: str, page: int = 1) -> str:
        if not filename or self.s3 is None:
            return ""
        try:
            return self.s3.url_for(filename, page)
        except Exception:  # noqa: BLE001 - PDF links are optional
            return ""

    def standards(self, query: str = "") -> list[dict[str, Any]]:
        needle = query.strip().lower()
        result: list[dict[str, Any]] = []
        for item in build_corpus_standards(self._documents()):
            if needle and needle not in item.gost_number.lower() and needle not in item.title.lower():
                continue
            result.append(
                {
                    "gost_number": item.gost_number,
                    "title": item.title,
                    "doc_type": item.doc_type,
                    "documents": item.documents,
                    "chunks": item.chunks,
                    "filename": item.filename,
                    "pdf_url": self._pdf(item.filename),
                }
            )
        return result

    def find_standard(self, gost: str) -> dict[str, Any] | None:
        target = _norm_gost(gost)
        for item in self.standards():
            if _norm_gost(item["gost_number"]) == target:
                return item
        return None

    def outline(self, gost: str) -> dict | None:
        if self.kb is None:
            return None
        return self.kb.outline(gost)

    def _is_section_heading(self, term: dict) -> bool:
        name = str(term.get("term") or "").strip().lower()
        return name.startswith("термины") or name in {"общие положения", "термины и определения"}

    def terms(self, *, gost: str | None = None, query: str = "") -> list[dict[str, Any]]:
        merged: dict[tuple[str, str], dict[str, Any]] = {}
        needle = query.strip().lower()
        if self.term_catalog is not None:
            source = (
                self.term_catalog.for_gost(gost)
                if gost
                else list(self.term_catalog.terms)
            )
            for term in source:
                if gost and _norm_gost(term.gost_number) != _norm_gost(gost):
                    continue
                if needle and needle not in term.term.lower() and needle not in term.definition.lower():
                    continue
                merged[(_norm_gost(term.gost_number), term.clause)] = {
                    "term": term.term,
                    "term_norm": term.term.lower(),
                    "definition": term.definition,
                    "gost": term.gost_number,
                    "clause": term.clause,
                    "page": term.page,
                    "source_file": term.file,
                }
        if self.kb is not None:
            if query:
                kbitems = self.kb.find_term(query, gost, limit=50)
            else:
                kbitems = [
                    term
                    for term in self.kb.terms
                    if not gost or _norm_gost(term.get("gost", "")) == _norm_gost(gost)
                ]
            for term in kbitems:
                if self._is_section_heading(term):
                    continue
                key = (_norm_gost(term.get("gost", "")), str(term.get("clause", "")))
                merged.setdefault(
                    key,
                    {
                        "term": term.get("term", ""),
                        "term_norm": term.get("term_norm", ""),
                        "definition": term.get("definition", ""),
                        "gost": term.get("gost", ""),
                        "clause": term.get("clause", ""),
                        "page": term.get("page", 0),
                        "source_file": term.get("source_file", ""),
                    },
                )
        return sorted(
            merged.values(),
            key=lambda item: (_norm_gost(item["gost"]), item["clause"]),
        )


    def links(self, gost: str) -> dict[str, Any]:
        if self.kb is None:
            return {"gost": gost, "outgoing": [], "incoming": []}
        return self.kb.neighbors(gost)

    def latest_audit(self) -> dict[str, Any] | None:
        roots = [Path(self.settings.reports_dir), Path("docs/reports")]
        candidates: list[Path] = []
        for root in roots:
            if root.is_dir():
                candidates.extend(root.rglob("manifest.json"))
        if not candidates:
            return None
        latest = max(candidates, key=lambda item: item.stat().st_mtime)
        try:
            data = json.loads(latest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return {
            "path": str(latest),
            "product_version": data.get("product_version"),
            "coverage": data.get("coverage"),
            "compliance_applicable": data.get("compliance_applicable"),
            "requirements_total": data.get("requirements_total"),
            "mtime": datetime.fromtimestamp(latest.stat().st_mtime, UTC),
        }
