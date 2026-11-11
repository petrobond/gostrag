"""Evaluate retrieval recall@k on the gold set without LLM generation."""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.embeddings.factory import get_embedder  # noqa: E402
from app.rag.chunk_store import ChunkStore  # noqa: E402
from app.rag.retriever import Retriever  # noqa: E402
from app.retrieval.bm25 import BM25Index  # noqa: E402
from app.storage.qdrant import QdrantStore  # noqa: E402

SOURCE_RE = re.compile(r"(.+?),\s*п\.\s*([\d.]+)")
APPENDIX_RE = re.compile(r"(.+?),\s*приложение\s+([А-ЯA-Z]+)", re.IGNORECASE)


def parse_source(text: str) -> tuple[str, str, str] | None:
    match = SOURCE_RE.match(text)
    if match:
        return match.group(1).strip(), "clause", match.group(2).strip()
    match = APPENDIX_RE.match(text)
    if match:
        return match.group(1).strip(), "appendix", match.group(2).strip()
    return None


async def main(gold_path: Path, corpus: Path, index: Path, qdrant_url: str, top_k: int) -> None:
    settings = get_settings()
    bm25 = BM25Index.load(index / "bm25.pkl")
    qdrant = QdrantStore(qdrant_url, settings.qdrant_collection)
    chunks = ChunkStore(corpus)
    retriever = Retriever(settings, get_embedder(settings), bm25, qdrant, chunks)

    gold = yaml.safe_load(gold_path.read_text(encoding="utf-8"))
    hits = 0
    total = 0
    misses: list[str] = []
    try:
        for item in gold["questions"]:
            sources = [parse_source(s) for s in item.get("expected_sources", [])]
            sources = [s for s in sources if s]
            if not sources:
                continue
            total += 1
            retrieved = await retriever.retrieve(item["question"], top_k=top_k)
            found = False
            for chunk in retrieved:
                for gost, kind, value in sources:
                    if chunk.gost_number != gost:
                        continue
                    if kind == "clause" and (
                        chunk.clause == value or chunk.clause.startswith(value + ".")
                    ):
                        found = True
                    if kind == "appendix" and chunk.section.lower().endswith(value.lower()):
                        found = True
            if found:
                hits += 1
            else:
                misses.append(item["id"])
                print(f"MISS {item['id']}: {item['question'][:80]}")
                for chunk in retrieved[:3]:
                    print(f"   got {chunk.gost_number} п.{chunk.clause}")
    finally:
        await qdrant.close()

    print(f"recall@{top_k}: {hits}/{total} = {hits / max(total, 1):.3f}")
    print("misses:", misses)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", default="eval/gold_set.yaml")
    parser.add_argument("--corpus", default="data/corpus")
    parser.add_argument("--index", default="data/index")
    parser.add_argument("--qdrant-url", default="http://localhost:6333")
    parser.add_argument("--top-k", type=int, default=6)
    args = parser.parse_args()
    asyncio.run(main(Path(args.gold), Path(args.corpus), Path(args.index), args.qdrant_url, args.top_k))
