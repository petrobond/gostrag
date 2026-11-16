"""Structured catalog of terms defined in GOST clause 3."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from app.rag.generator import Citation

TERM_CLAUSE_RE = re.compile(r"^3\.(\d+)\.(\d+)$")
SECTION_CLAUSE_RE = re.compile(r"^3\.(\d+)$")


def norm_gost(value: str) -> str:
    return re.sub(r"[\s—–-]+", "", (value or "")).lower()


def _natural(value: str) -> tuple[int, ...]:
    return tuple(int(item) for item in re.findall(r"\d+", value or ""))


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


@dataclass(frozen=True, slots=True)
class CorpusTerm:
    gost_number: str
    clause: str
    term: str
    definition: str
    page: int
    file: str
    section: str
    section_title: str


class TermCatalog:
    """Build term inventory from corpus chunks; no separate index required."""

    def __init__(self, rows: Iterable[Mapping[str, Any]]) -> None:
        terms: dict[tuple[str, str], CorpusTerm] = {}
        section_titles: dict[tuple[str, str], str] = {}
        section_pages: dict[tuple[str, str], int] = {}
        section_files: dict[tuple[str, str], str] = {}

        for raw in rows:
            if raw.get("chunk_type", "clause") != "clause":
                continue
            gost = str(raw.get("gost_number") or "").strip()
            clause = str(raw.get("clause") or "").split("#", 1)[0].strip()
            title = str(raw.get("clause_title") or "").strip()
            if not gost or not clause or not title:
                continue
            page = int(raw.get("page", 0) or 0)
            file = str((raw.get("provenance") or {}).get("file", ""))
            section_match = SECTION_CLAUSE_RE.match(clause)
            if section_match:
                key = (norm_gost(gost), clause)
                section_titles[key] = title
                section_pages[key] = page
                section_files[key] = file
                continue
            term_match = TERM_CLAUSE_RE.match(clause)
            if not term_match:
                continue
            parts = re.split(r"[:—–]", title, maxsplit=1)
            if len(parts) != 2:
                continue
            term = parts[0].strip(" .")
            if len(term) < 2:
                continue
            section = f"3.{term_match.group(1)}"
            candidate = CorpusTerm(
                gost_number=gost,
                clause=clause,
                term=term,
                definition=str(raw.get("text") or "").strip(),
                page=page,
                file=file,
                section=section,
                section_title=section_titles.get((norm_gost(gost), section), ""),
            )
            key = (norm_gost(gost), clause)
            current = terms.get(key)
            if current is None or len(candidate.definition) > len(current.definition):
                terms[key] = candidate

        self.terms = sorted(
            terms.values(),
            key=lambda item: (
                norm_gost(item.gost_number),
                _natural(item.clause),
                item.clause,
            ),
        )
        self._by_gost: dict[str, list[CorpusTerm]] = defaultdict(list)
        for term in self.terms:
            term = CorpusTerm(
                gost_number=term.gost_number,
                clause=term.clause,
                term=term.term,
                definition=term.definition,
                page=term.page,
                file=term.file,
                section=term.section,
                section_title=section_titles.get(
                    (norm_gost(term.gost_number), term.section), term.section_title
                ),
            )
            self._by_gost[norm_gost(term.gost_number)].append(term)
        self._section_titles = {key: value for key, value in section_titles.items()}
        self._section_pages = section_pages
        self._section_files = section_files

    def has_gost(self, gost_number: str) -> bool:
        return bool(self._by_gost.get(norm_gost(gost_number)))

    def for_gost(self, gost_number: str) -> list[CorpusTerm]:
        return list(self._by_gost.get(norm_gost(gost_number), []))

    def sections(self, gost_number: str) -> list[str]:
        return sorted(
            {item.section for item in self.for_gost(gost_number)},
            key=_natural,
        )

    def format_inventory(self, gost_number: str) -> str:
        terms = self.for_gost(gost_number)
        if not terms:
            return ""
        lines = [
            f"В {gost_number} раздел 3 «Термины и определения» — "
            f"{len(terms)} "
            f"{_plural(len(terms), 'термин', 'термина', 'терминов')}."
        ]
        grouped: dict[str, list[CorpusTerm]] = defaultdict(list)
        for term in terms:
            grouped[term.section].append(term)
        for section in sorted(grouped, key=_natural):
            group = grouped[section]
            title = self._section_titles.get(
                (norm_gost(gost_number), section), group[0].section_title
            )
            suffix = f" {title}" if title else ""
            lines.extend(["", f"{section}{suffix} ({len(group)}):"])
            lines.extend(f"• {item.clause} {item.term}" for item in group)
        lines.extend(
            [
                "",
                "Определения указаны в соответствующих пунктах раздела 3; "
                "можно спросить «что такое <термин>».",
            ]
        )
        return "\n".join(lines)

    def section_citations(self, gost_number: str) -> list[Citation]:
        citations: list[Citation] = []
        for section in self.sections(gost_number):
            key = (norm_gost(gost_number), section)
            title = self._section_titles.get(key, f"Раздел {section}")
            page = self._section_pages.get(key, 0)
            file = self._section_files.get(key, "")
            if not page:
                group = [
                    item for item in self.for_gost(gost_number) if item.section == section
                ]
                page = group[0].page if group else 0
                file = file or (group[0].file if group else "")
            citations.append(
                Citation(
                    gost=gost_number,
                    clause=section,
                    page=page,
                    quote=title[:200],
                    file=file,
                    valid=True,
                    page_valid=True,
                    quote_valid=True,
                )
            )
        return citations

