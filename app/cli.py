from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import shutil
import tarfile
import time
import uuid
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import boto3
from qdrant_client.http import models as qm

from app.config import get_settings
from app.embeddings.factory import get_embedder
from app.ingest.chunk import build_chunks
from app.ingest.parse import parse_document
from app.retrieval.bm25 import BM25Index
from app.storage.qdrant import QdrantStore


def cmd_ingest(args: argparse.Namespace) -> None:
    settings = get_settings()
    source = Path(args.source or settings.data_source_dir)
    out_dir = Path(args.out or settings.data_corpus_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(source.rglob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"no PDF found in {source}")

    documents: list[dict] = []
    all_chunks: list[dict] = []
    errors: list[dict] = []
    skipped_duplicates: list[str] = []
    seen_hashes: dict[str, str] = {}
    now = datetime.now(UTC).isoformat()

    unique_pdfs = []
    for pdf in pdfs:
        digest = hashlib.md5(pdf.read_bytes()).hexdigest()
        if digest in seen_hashes:
            skipped_duplicates.append(f"{pdf.name} == {seen_hashes[digest]}")
            continue
        seen_hashes[digest] = pdf.name
        unique_pdfs.append(pdf)

    for pdf in unique_pdfs:
        try:
            doc = parse_document(pdf)
        except Exception as exc:  # noqa: BLE001
            errors.append({"file": str(pdf), "error": str(exc)})
            continue
        chunks = build_chunks(doc, settings.corpus_version, pdf.name)
        for chunk in chunks:
            chunk.provenance["extracted_at"] = now
        meta = asdict(doc.meta) | {"clauses": len(doc.clauses), "chunks": len(chunks)}
        documents.append(meta)
        all_chunks.extend(c.to_dict() for c in chunks)

    with (out_dir / "documents.json").open("w", encoding="utf-8") as fh:
        json.dump(documents, fh, ensure_ascii=False, indent=2)

    with (out_dir / "chunks.jsonl").open("w", encoding="utf-8") as fh:
        for chunk in all_chunks:
            fh.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    hashes = Counter(c["text_hash"] for c in all_chunks)
    report = {
        "generated_at": now,
        "corpus_version": settings.corpus_version,
        "documents_total": len(documents),
        "documents_failed": errors,
        "duplicate_files_skipped": skipped_duplicates,
        "clauses_total": sum(d["clauses"] for d in documents),
        "chunks": chunk_stats_from_dicts(all_chunks),
        "duplicate_text_hashes": sum(1 for v in hashes.values() if v > 1),
        "documents_without_chunks": [d["doc_id"] for d in documents if d["chunks"] == 0],
        "top_documents_by_chunks": sorted(
            ((d["doc_id"], d["chunks"]) for d in documents), key=lambda x: -x[1]
        )[:10],
    }
    with (out_dir / "quality_report.json").open("w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    print(json.dumps(report, ensure_ascii=False, indent=2))


def chunk_stats_from_dicts(chunks: list[dict]) -> dict:
    if not chunks:
        return {"count": 0}
    lengths = [len(c["text"]) for c in chunks]
    return {
        "count": len(chunks),
        "min_chars": min(lengths),
        "max_chars": max(lengths),
        "avg_chars": round(sum(lengths) / len(lengths), 1),
        "unique_docs": len({c["doc_id"] for c in chunks}),
    }


def cmd_stats(args: argparse.Namespace) -> None:
    settings = get_settings()
    path = Path(args.out or settings.data_corpus_dir) / "quality_report.json"
    print(path.read_text(encoding="utf-8"))


def _load_unique_chunks(corpus_dir: Path) -> list[dict]:
    rows = [json.loads(line) for line in (corpus_dir / "chunks.jsonl").open(encoding="utf-8")]
    seen: set[str] = set()
    unique: list[dict] = []
    for row in rows:
        if row["text_hash"] in seen:
            continue
        seen.add(row["text_hash"])
        unique.append(row)
    return unique


async def _embed_and_upsert(
    chunks: list[dict],
    embedder,
    qdrant_url: str,
    collection: str,
    batch_size: int = 32,
) -> int:
    store = QdrantStore(qdrant_url, collection)
    await store.ensure_collection(embedder.dim)
    total = 0
    started = time.perf_counter()
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        vectors = await embedder.aembed_documents([row["text"] for row in batch])
        points = [
            qm.PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, row["chunk_id"])),
                vector=vector,
                payload=row,
            )
            for row, vector in zip(batch, vectors, strict=True)
        ]
        await store.upsert(points)
        total += len(points)
        elapsed = time.perf_counter() - started
        print(f"embedded {total}/{len(chunks)} in {elapsed:.1f}s ({total / elapsed:.1f}/s)", flush=True)
    await store.close()
    return total


def cmd_embed(args: argparse.Namespace) -> None:
    settings = get_settings()
    corpus_dir = Path(args.corpus or settings.data_corpus_dir)
    index_dir = Path(args.index or "data/index")
    index_dir.mkdir(parents=True, exist_ok=True)
    chunks = _load_unique_chunks(corpus_dir)
    if not chunks:
        raise SystemExit("no chunks found")
    print(f"unique chunks: {len(chunks)}")

    embedder = get_embedder(settings)
    qdrant_url = args.qdrant_url or settings.qdrant_url
    total = asyncio.run(
        _embed_and_upsert(chunks, embedder, qdrant_url, settings.qdrant_collection)
    )

    bm25 = BM25Index([row["chunk_id"] for row in chunks], [row["text"] for row in chunks])
    bm25.save(index_dir / "bm25.pkl")

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "embedding_provider": settings.embedding_provider,
        "embedding_dim": embedder.dim,
        "chunks_total": len(chunks),
        "chunks_embedded": total,
        "collection": settings.qdrant_collection,
        "qdrant_url": qdrant_url,
    }
    (index_dir / "embed_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))



def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def cmd_data_fetch(args: argparse.Namespace) -> None:
    settings = get_settings()
    bucket = args.bucket or settings.s3_bucket
    if not bucket:
        raise SystemExit("S3_BUCKET is not configured")
    version = args.version
    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)
    staging = dest / f".fetch-{version}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    )
    base = f"{args.prefix.strip('/')}/{version}"
    archive = staging / f"data-{version}.tar.gz"
    manifest_path = staging / f"manifest-{version}.json"
    client.download_file(bucket, f"{base}/{manifest_path.name}", str(manifest_path))
    client.download_file(bucket, f"{base}/{archive.name}", str(archive))

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if _sha256(archive) != manifest["archive_sha256"]:
        raise SystemExit("archive checksum mismatch")
    extracted = staging / "extract"
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(extracted, filter="data")
    for name in ("corpus", "index", "kb"):
        if not (extracted / name).exists():
            raise SystemExit(f"data archive has no {name}/")

    backup = dest / "backups" / f"data-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    backup.mkdir(parents=True, exist_ok=True)
    for name in ("corpus", "index", "kb"):
        target = dest / name
        if target.exists():
            shutil.copytree(target, backup / name)
        target.mkdir(parents=True, exist_ok=True)
        for child in target.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        shutil.copytree(extracted / name, target, dirs_exist_ok=True)
    print(
        json.dumps(
            {
                "version": version,
                "corpus_version": manifest.get("corpus_version"),
                "counts": manifest.get("counts"),
                "backup": str(backup),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="gostrag")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="parse PDFs into chunks")
    ingest.add_argument("--source", default="")
    ingest.add_argument("--out", default="")
    ingest.set_defaults(func=cmd_ingest)

    stats = sub.add_parser("stats", help="print quality report")
    stats.add_argument("--out", default="")
    stats.set_defaults(func=cmd_stats)

    embed = sub.add_parser("embed", help="build embeddings and indexes")
    embed.add_argument("--corpus", default="")
    embed.add_argument("--index", default="data/index")
    embed.add_argument("--qdrant-url", default="")
    embed.set_defaults(func=cmd_embed)

    fetch = sub.add_parser("data-fetch", help="download a data artifact from S3")
    fetch.add_argument("--version", required=True)
    fetch.add_argument("--bucket", default="")
    fetch.add_argument("--prefix", default="data")
    fetch.add_argument("--dest", default="/data")
    fetch.set_defaults(func=cmd_data_fetch)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
