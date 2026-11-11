"""Ask one question against the local index."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.rag.service import AskService  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("question")
    parser.add_argument("--corpus", default="data/corpus")
    parser.add_argument("--index", default="data/index")
    parser.add_argument("--qdrant-url", default="http://localhost:6333")
    parser.add_argument("--top-k", type=int, default=6)
    args = parser.parse_args()

    service = AskService(
        get_settings(),
        Path(args.corpus),
        Path(args.index),
        args.qdrant_url,
    )
    try:
        result = await service.ask(args.question, top_k=args.top_k)
    finally:
        await service.close()

    print("=" * 80)
    print("QUESTION:", args.question)
    print("MODEL:", result.answer.model, result.answer.provider)
    print("LATENCY:", result.latency_ms, "ms")
    print("REFUSED:", result.answer.refused, "CONFIDENCE:", result.answer.confidence)
    print("-" * 80)
    print(result.answer.answer)
    print("-" * 80)
    print("CITATIONS:")
    for citation in result.answer.citations:
        print(
            f"  [{'OK' if citation.valid else 'INVALID'}] {citation.gost}, "
            f"п. {citation.clause}, с. {citation.page}: {citation.quote[:120]}"
        )
    print("RETRIEVED:")
    for chunk in result.chunks:
        print(f"  {chunk.score:.4f} {chunk.chunk_id} | {chunk.text[:100]}")


if __name__ == "__main__":
    asyncio.run(main())
