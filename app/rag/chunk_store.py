from __future__ import annotations

import json
from pathlib import Path


class ChunkStore:
    """In-memory chunk payloads keyed by chunk_id."""

    def __init__(self, corpus_dir: Path) -> None:
        self.by_id: dict[str, dict] = {}
        path = corpus_dir / "chunks.jsonl"
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                row = json.loads(line)
                self.by_id[row["chunk_id"]] = row

    def get(self, chunk_id: str) -> dict | None:
        return self.by_id.get(chunk_id)

    def __len__(self) -> int:
        return len(self.by_id)
