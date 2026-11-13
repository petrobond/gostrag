from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

TOKEN_RE = re.compile(r"[а-яёa-z0-9]+", re.IGNORECASE)
STOP_WORDS = {
    "что",
    "такое",
    "дай",
    "определение",
    "понимается",
    "под",
    "гост",
    "стандарт",
    "по",
    "в",
    "и",
    "на",
    "какие",
    "какой",
    "каким",
    "этапы",
    "этап",
    "включает",
    "включать",
    "перечисли",
    "приведены",
    "приведен",
    "назови",
    "назовите",
    "опиши",
    "опишите",
    "сколько",
    "чем",
    "отличаются",
    "разница",
    "для",
    "при",
    "как",
    "или",
    "их",
    "его",
    "ее",
    "это",
    "эти",
}


def _hash_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _stem(word: str) -> str:
    return word[:5]


def _clause_key(clause: str) -> tuple:
    """Sort clauses numerically: 6.2 < 6.10, non-numeric parts go last."""
    parts = []
    for part in clause.replace("#", ".").split("."):
        parts.append((0, int(part), "") if part.isdigit() else (1, 0, part))
    return tuple(parts)


class ChunkStore:
    """In-memory chunk payloads keyed by chunk_id, GOST and clause."""

    def __init__(self, corpus_dir: Path) -> None:
        self.by_id: dict[str, dict] = {}
        self.by_key: dict[tuple[str, str], dict] = {}
        self.by_gost: dict[str, list[dict]] = {}
        self.by_doc: dict[str, list[dict]] = {}
        self.by_section: dict[tuple[str, str], list[dict]] = {}
        self._title_tokens: dict[str, set[str]] = {}
        path = corpus_dir / "chunks.jsonl"
        merged: dict[str, dict] = {}
        order: list[str] = []
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                row = json.loads(line)
                chunk_id = row["chunk_id"]
                if chunk_id in merged:
                    # Duplicate clause chunks (same chunk_id, different parser output)
                    # must stay in one payload; otherwise the tail with identifiers is lost.
                    current = merged[chunk_id]
                    current["text"] = f"{current['text']}\n{row['text']}"
                    current["text_hash"] = _hash_text(current["text"])
                else:
                    merged[chunk_id] = row
                    order.append(chunk_id)
        for chunk_id in order:
            row = merged[chunk_id]
            self.by_id[row["chunk_id"]] = row
            self.by_key[(row["gost_number"], row["clause"])] = row
            self.by_gost.setdefault(row["gost_number"], []).append(row)
            self.by_doc.setdefault(row["doc_id"], []).append(row)
            self.by_section.setdefault((row["doc_id"], row.get("section", "")), []).append(row)
            title = row.get("clause_title", "") or row["text"][:120]
            self._title_tokens[row["chunk_id"]] = {
                _stem(token) for token in TOKEN_RE.findall(title.lower())
            }


    def get(self, chunk_id: str) -> dict | None:
        return self.by_id.get(chunk_id)

    def find(self, gost_number: str | None, clause: str | None) -> list[dict]:
        if gost_number and clause:
            row = self.by_key.get((gost_number, clause))
            return [row] if row else []
        if gost_number:
            return self.by_gost.get(gost_number, [])
        return []

    def find_fuzzy(self, gost_number: str, clause: str) -> list[dict]:
        """Match by normalized GOST number and clause prefix (6.2.5 -> 6.2.5, 6.2.5.1, 6.2.5#p1)."""
        norm = _norm_gost(gost_number)
        matches = [
            row
            for (gost, cl), row in self.by_key.items()
            if _norm_gost(gost) == norm
            and (cl == clause or cl.startswith(clause + ".") or cl.startswith(clause + "#"))
        ]
        return sorted(matches, key=lambda row: row["clause"])[:3]

    def find_term(self, term: str, gost_number: str | None = None, limit: int = 3) -> list[dict]:
        """Find definition chunks whose clause title matches the term stems."""
        tokens = [
            _stem(token)
            for token in TOKEN_RE.findall(term.lower())
            if token not in STOP_WORDS and len(token) >= 2
        ]
        if not tokens:
            return []
        scored: list[tuple[int, int, dict]] = []
        for chunk_id, title_tokens in self._title_tokens.items():
            row = self.by_id[chunk_id]
            if gost_number and row["gost_number"] != gost_number:
                continue
            score = sum(1 for token in tokens if token in title_tokens)
            if score == len(tokens):
                prefix_bonus = 1 if _stem(term.lower().split()[0]) in _stem(row.get("clause_title", "").lower()[:40]) else 0
                scored.append((score + prefix_bonus, -len(row["text"]), row))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [row for _, _, row in scored[:limit]]

    def find_section_by_title(
        self, question: str, gost_number: str | None = None
    ) -> tuple[str, str] | None:
        """Map a question phrase to a section title ("процесс управления качеством")."""
        q_tokens = {
            _stem(token)
            for token in TOKEN_RE.findall(question.lower())
            if token not in STOP_WORDS and len(token) >= 3
        }
        if len(q_tokens) < 3:
            return None
        best: tuple[float, int, int, int, str, str] | None = None
        seen: set[tuple[str, str]] = set()
        for doc_id, rows in self.by_doc.items():
            section_counts: dict[str, int] = {}
            for row in rows:
                if row.get("section"):
                    section_counts[row["section"]] = section_counts.get(row["section"], 0) + 1
            for row in rows:
                if gost_number and row["gost_number"] != gost_number:
                    continue
                section = row.get("section", "")
                title = row.get("section_title", "")
                key = (doc_id, section)
                if not section or not title or key in seen:
                    continue
                seen.add(key)
                children = section_counts.get(section, 1)
                if children < 2:
                    continue
                title_tokens = {
                    _stem(token)
                    for token in TOKEN_RE.findall(title.lower())
                    if token not in STOP_WORDS and len(token) >= 3
                }
                if len(title_tokens) < 3:
                    continue
                matched = len(q_tokens & title_tokens)
                if matched < 3:
                    continue
                extra = len(title_tokens - q_tokens)
                score = matched - 0.5 * extra
                # Prefer the shortest (most general) title: "Структура процесса..."
                # over "Процесс ... для аналитики" / "... для машинного обучения".
                if best is None or (score, -len(title), children, -extra) > (
                    best[0],
                    best[1],
                    best[2],
                    best[3],
                ):
                    best = (score, -len(title), children, extra, doc_id, section)
        if best is None or best[0] < 2.0:
            return None
        return best[4], best[5].split(".")[0]

    def find_sections_by_title(
        self,
        question: str,
        gost_number: str | None = None,
        min_matched: int = 2,
        limit: int = 1,
    ) -> list[tuple[str, str]]:
        """Return up to `limit` sections whose title overlaps the question."""
        q_tokens = {
            _stem(token)
            for token in TOKEN_RE.findall(question.lower())
            if token not in STOP_WORDS and len(token) >= 3
        }
        if len(q_tokens) < min_matched:
            return []
        ranked: list[tuple[float, int, int, str, str]] = []
        seen: set[tuple[str, str]] = set()
        for doc_id, rows in self.by_doc.items():
            section_counts: dict[str, int] = {}
            for row in rows:
                if row.get("section"):
                    section_counts[row["section"]] = section_counts.get(row["section"], 0) + 1
            for row in rows:
                if gost_number and row["gost_number"] != gost_number:
                    continue
                section = row.get("section", "")
                title = row.get("section_title", "")
                key = (doc_id, section)
                if not section or not title or key in seen:
                    continue
                seen.add(key)
                children = section_counts.get(section, 1)
                if children < 2:
                    continue
                title_tokens = {
                    _stem(token)
                    for token in TOKEN_RE.findall(title.lower())
                    if token not in STOP_WORDS and len(token) >= 3
                }
                matched = len(q_tokens & title_tokens)
                if matched < min_matched:
                    continue
                extra = len(title_tokens - q_tokens)
                score = matched - 0.5 * extra
                ranked.append((score, -len(title), children, doc_id, section))
        ranked.sort(reverse=True)
        return [(doc_id, section) for _, _, _, doc_id, section in ranked[:limit]]

    def find_appendix(self, gost_number: str, appendix: str) -> list[dict]:
        suffix = appendix.lower()
        result = []
        for row in self.by_gost.get(gost_number, []):
            section = row.get("section", "").lower()
            head = row["text"][:200].lower()
            if section.endswith(suffix) or f"приложение {suffix}" in head:
                result.append(row)
        return result

    def section_chunks(self, doc_id: str, section: str) -> list[dict]:
        rows = self.by_section.get((doc_id, section), [])
        return sorted(rows, key=lambda row: _clause_key(row["clause"]))

    def find_meta(self, gost_number: str) -> list[dict]:
        rows = [
            row
            for row in self.by_gost.get(gost_number, [])
            if row.get("chunk_type") == "meta"
        ]
        return rows[:1]

    def meta_by_doc_type(self) -> list[dict]:
        """One representative meta chunk per document type (ГОСТ Р, ПНСТ)."""
        result: dict[str, dict] = {}
        for row in self.by_id.values():
            if row.get("chunk_type") == "meta":
                result.setdefault(row.get("doc_type", ""), row)
        return list(result.values())

    def table_chunks(self, gost_number: str, table_number: str | None = None) -> list[dict]:
        rows = [
            row
            for row in self.by_gost.get(gost_number, [])
            if row.get("chunk_type") == "table"
        ]
        if table_number is not None:
            norm = _norm_table_number(table_number)
            rows = [
                row
                for row in rows
                if _norm_table_number(row.get("table_number", "")) == norm
            ]
        rows.sort(
            key=lambda row: (
                str(row.get("table_id", "")),
                int(row.get("row_start", 0) or 0),
                int(row.get("part", 1) or 1),
            )
        )
        return rows

    def clause_siblings(self, doc_id: str, clause: str, limit: int = 12) -> list[dict]:
        """All chunks of the same top-level subsection: "4.2" -> 4., 4.1 ... 4.7."""
        head = clause.split(".")[0]
        if not head.isdigit():
            return []
        rows = [
            row
            for row in self.by_doc.get(doc_id, [])
            if row["clause"].split(".")[0] == head
        ]
        rows.sort(key=lambda row: _clause_key(row["clause"]))
        return rows[:limit]

    def __len__(self) -> int:
        return len(self.by_id)


def _norm_gost(value: str) -> str:
    return re.sub(r"[\s—–-]+", "", value).lower()


def _norm_table_number(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


