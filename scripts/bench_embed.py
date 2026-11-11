"""Benchmark embedding and Qdrant upsert separately."""

from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

from qdrant_client.http import models as qm

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.embeddings.factory import get_embedder  # noqa: E402
from app.storage.qdrant import QdrantStore  # noqa: E402


async def main() -> None:
    settings = get_settings()
    rows = [json.loads(line) for line in Path("data/corpus/chunks.jsonl").open(encoding="utf-8")][:32]
    texts = [row["text"] for row in rows]

    embedder = get_embedder(settings)
    started = time.perf_counter()
    vectors = embedder.embed_documents(texts)
    embed_time = time.perf_counter() - started
    print(f"embed {len(texts)} docs: {embed_time:.2f}s ({len(texts) / embed_time:.2f} docs/s)")

    store = QdrantStore("http://localhost:6333", settings.qdrant_collection)
    await store.ensure_collection(embedder.dim)
    points = [
        qm.PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, row["chunk_id"])),
            vector=vector,
            payload=row,
        )
        for row, vector in zip(rows, vectors, strict=True)
    ]
    started = time.perf_counter()
    await store.upsert(points)
    upsert_time = time.perf_counter() - started
    print(f"upsert {len(points)} points: {upsert_time:.2f}s")
    await store.close()


if __name__ == "__main__":
    asyncio.run(main())
