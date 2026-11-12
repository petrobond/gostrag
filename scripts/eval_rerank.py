"""A/B: Cloud.ru reranker on gold v3 retrieval."""

from __future__ import annotations

import asyncio
import statistics
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import get_settings  # noqa: E402
from app.embeddings.factory import get_embedder  # noqa: E402
from app.rag.chunk_store import ChunkStore  # noqa: E402
from app.rag.reranker import CloudRuReranker  # noqa: E402
from app.rag.retriever import Retriever  # noqa: E402
from app.retrieval.bm25 import BM25Index  # noqa: E402
from app.storage.qdrant import QdrantStore  # noqa: E402
from eval_retrieval import matches_source, parse_source  # noqa: E402


async def main() -> None:
    settings = get_settings()
    gold = yaml.safe_load(Path("eval/gold_set_v3.yaml").read_text(encoding="utf-8"))
    embedder = get_embedder(settings)
    bm25 = BM25Index.load(Path("data/index/bm25.pkl"))
    qdrant = QdrantStore(settings.qdrant_url, settings.qdrant_collection)
    chunks = ChunkStore(Path("data/corpus"))
    retriever = Retriever(settings, embedder, bm25, qdrant, chunks)
    reranker = CloudRuReranker(settings)

    total = base_hits = rerank_hits = top1_base = top1_rerank = 0
    latencies: list[float] = []
    tokens = 0
    try:
        for item in gold["questions"]:
            sources = [parse_source(source) for source in item.get("expected_sources", [])]
            sources = [source for source in sources if source]
            if not sources:
                continue
            total += 1
            candidates = await retriever.retrieve(item["question"], top_k=settings.rerank_top_n)
            base = candidates[:8]
            started = time.perf_counter()
            scores = await reranker.ascore(item["question"], [chunk.text for chunk in candidates])
            latencies.append(time.perf_counter() - started)
            tokens += reranker.last_tokens
            reranked = [
                chunk
                for _, chunk in sorted(
                    zip(scores, candidates), key=lambda pair: pair[0], reverse=True
                )
            ][:8]
            if any(matches_source(chunk, *source) for chunk in base for source in sources):
                base_hits += 1
            if any(matches_source(chunk, *source) for chunk in reranked for source in sources):
                rerank_hits += 1
            if base and any(matches_source(base[0], *source) for source in sources):
                top1_base += 1
            if reranked and any(matches_source(reranked[0], *source) for source in sources):
                top1_rerank += 1
    finally:
        await qdrant.close()

    print(f"questions: {total}")
    print(f"recall@8 base: {base_hits}/{total} = {base_hits / max(total, 1):.3f}")
    print(f"recall@8 rerank: {rerank_hits}/{total} = {rerank_hits / max(total, 1):.3f}")
    print(f"top1 base: {top1_base}/{total}; rerank: {top1_rerank}/{total}")
    print(
        f"rerank latency p50: {statistics.median(latencies) * 1000:.0f} ms; "
        f"p95: {sorted(latencies)[int(0.95 * len(latencies)) - 1] * 1000:.0f} ms"
    )
    print(f"rerank tokens: {tokens}")


if __name__ == "__main__":
    asyncio.run(main())
