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
from app.rag.query_classifier import extract_gosts  # noqa: E402
from app.rag.retriever import Retriever  # noqa: E402
from app.retrieval.bm25 import BM25Index  # noqa: E402
from app.storage.qdrant import QdrantStore  # noqa: E402

SOURCE_RE = re.compile(r"(.+?),\s*п\.\s*(\d+(?:\.\d+)*)\s*[–-]\s*(\d+(?:\.\d+)*)")
CLAUSE_RE = re.compile(r"(.+?),\s*п\.\s*(\d+(?:\.\d+)*)")
SECTION_RE = re.compile(r"(.+?),\s*раздел\s+(\d+(?:\.\d+)*)")
TABLE_RE = re.compile(r"(.+?),\s*таблиц[аы]\s+([\wА-Яа-яЁё.-]+)")
APPENDIX_RE = re.compile(r"(.+?),\s*приложение\s+([А-ЯA-Z]+)", re.IGNORECASE)
BARE_RE = re.compile(r"^((?:ГОСТ\s*Р|ПНСТ)\s*[\d.]+(?:\s*[—–-]\s*\d{4})?)$")
DOC_TYPE_RE = re.compile(r"^(ГОСТ\s*Р|ПНСТ)$")


def parse_source(text: str) -> tuple[str, str, object] | None:
    match = SOURCE_RE.match(text)
    if match:
        return match.group(1).strip(), "range", (match.group(2).strip(), match.group(3).strip())
    match = CLAUSE_RE.match(text)
    if match:
        return match.group(1).strip(), "clause", match.group(2).strip()
    match = SECTION_RE.match(text)
    if match:
        return match.group(1).strip(), "section", match.group(2).strip()
    match = TABLE_RE.match(text)
    if match:
        return match.group(1).strip(), "table", match.group(2).strip()
    match = APPENDIX_RE.match(text)
    if match:
        return match.group(1).strip(), "appendix", match.group(2).strip()
    match = BARE_RE.match(text.strip())
    if match:
        return match.group(1).strip(), "any", ""
    match = DOC_TYPE_RE.match(text.strip())
    if match:
        return match.group(1).strip(), "doc_type", ""
    return None


def _clause_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split(".") if part.isdigit())


def matches_source(chunk, gost: str, kind: str, value: object) -> bool:
    if kind == "doc_type":
        return chunk.gost_number.startswith(gost)
    if chunk.gost_number != gost:
        return False
    if kind == "any":
        return True
    if kind == "clause":
        clause = str(value)
        return chunk.clause == clause or chunk.clause.startswith(clause + ".")
    if kind == "range":
        start, end = value  # type: ignore[misc]
        base = chunk.clause.split("#")[0]
        try:
            current = _clause_tuple(base)
            return _clause_tuple(str(start)) <= current <= _clause_tuple(str(end))
        except ValueError:
            return chunk.clause.startswith(str(start) + ".")
    if kind == "section":
        section = str(value)
        return chunk.section == section or chunk.clause.startswith(section + ".")
    if kind == "table":
        expected = f"таблица{value}".lower().replace(" ", "")
        actual = chunk.clause.lower().replace(" ", "")
        return actual == expected
    if kind == "appendix":
        return chunk.section.lower().endswith(str(value).lower())
    return False


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
            gosts = extract_gosts(item["question"])
            if item.get("category") == "comparison" and len(gosts) >= 2:
                retrieved = await retriever.retrieve_comparison(
                    item["question"], gosts, top_k=top_k
                )
            else:
                retrieved = await retriever.retrieve(item["question"], top_k=top_k)
            found = False
            for chunk in retrieved:
                for gost, kind, value in sources:
                    if matches_source(chunk, gost, kind, value):
                        found = True
                        break
                if found:
                    break
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
