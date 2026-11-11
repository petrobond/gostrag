"""Remove Qdrant points that are not present in the current corpus."""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.storage.qdrant import QdrantStore  # noqa: E402


async def main() -> None:
    settings = get_settings()
    rows = [json.loads(line) for line in Path("data/corpus/chunks.jsonl").open(encoding="utf-8")]
    expected = {str(uuid.uuid5(uuid.NAMESPACE_URL, row["chunk_id"])) for row in rows}

    store = QdrantStore("http://localhost:6333", settings.qdrant_collection)
    existing: set[str] = set()
    offset = None
    while True:
        points, offset = await store.client.scroll(
            collection_name=settings.qdrant_collection,
            limit=256,
            offset=offset,
            with_payload=False,
        )
        existing.update(str(point.id) for point in points)
        if offset is None:
            break

    extra = existing - expected
    missing = expected - existing
    print(f"expected={len(expected)} existing={len(existing)} extra={len(extra)} missing={len(missing)}")
    if extra:
        await store.client.delete(
            collection_name=settings.qdrant_collection,
            points_selector=list(extra),
        )
        print(f"deleted {len(extra)} extra points")
    await store.close()


if __name__ == "__main__":
    asyncio.run(main())
