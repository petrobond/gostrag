from __future__ import annotations

import json
import re
from pathlib import Path


class ChunkStore:
    """In-memory chunk payloads keyed by chunk_id, GOST and clause."""

    def __init__(self, corpus_dir: Path) -> None:
        self.by_id: dict[str, dict] = {}
        self.by_key: dict[tuple[str, str], dict] = {}
        self.by_gost: dict[str, list[dict]] = {}
        self.by_section: dict[tuple[str, str], list[dict]] = {}
        path = corpus_dir / "chunks.jsonl"
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                row = json.loads(line)
                self.by_id[row["chunk_id"]] = row
                self.by_key[(row["gost_number"], row["clause"])] = row
                self.by_gost.setdefault(row["gost_number"], []).append(row)
                self.by_section.setdefault((row["doc_id"], row.get("section", "")), []).append(row)

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

    def section_chunks(self, doc_id: str, section: str) -> list[dict]:
        rows = self.by_section.get((doc_id, section), [])
        return sorted(rows, key=lambda row: row["clause"])

    def __len__(self) -> int:
        return len(self.by_id)


def _norm_gost(value: str) -> str:
    return re.sub(r"[\s—–-]+", "", value).lower()

