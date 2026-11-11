from __future__ import annotations

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
}


def _stem(word: str) -> str:
    return word[:5]


class ChunkStore:
    """In-memory chunk payloads keyed by chunk_id, GOST and clause."""

    def __init__(self, corpus_dir: Path) -> None:
        self.by_id: dict[str, dict] = {}
        self.by_key: dict[tuple[str, str], dict] = {}
        self.by_gost: dict[str, list[dict]] = {}
        self.by_section: dict[tuple[str, str], list[dict]] = {}
        self._title_tokens: dict[str, set[str]] = {}
        path = corpus_dir / "chunks.jsonl"
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                row = json.loads(line)
                self.by_id[row["chunk_id"]] = row
                self.by_key[(row["gost_number"], row["clause"])] = row
                self.by_gost.setdefault(row["gost_number"], []).append(row)
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
        return sorted(rows, key=lambda row: row["clause"])

    def __len__(self) -> int:
        return len(self.by_id)


def _norm_gost(value: str) -> str:
    return re.sub(r"[\s—–-]+", "", value).lower()


