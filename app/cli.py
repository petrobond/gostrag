from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import shutil
import sys
import tarfile
import time
import uuid
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
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


def _read_password() -> str:
    import getpass

    if sys.stdin.isatty():
        first = getpass.getpass("Пароль: ")
        second = getpass.getpass("Повторите пароль: ")
        if first != second:
            raise SystemExit("passwords do not match")
        return first
    return sys.stdin.readline().rstrip("\n")


def _web_base(settings) -> str:
    if settings.web_domain:
        return f"https://{settings.web_domain}"
    return "http://127.0.0.1:8000"


async def _web_pool(settings):
    import asyncpg

    return await asyncpg.create_pool(settings.postgres_dsn, min_size=1, max_size=2, timeout=10)


async def cmd_db_migrate(args: argparse.Namespace) -> None:
    del args
    from app.web.migrations import apply_migrations

    settings = get_settings()
    pool = await _web_pool(settings)
    try:
        applied = await apply_migrations(pool)
    finally:
        await pool.close()
    print(json.dumps({"applied": applied}, ensure_ascii=False))


async def cmd_web_user(args: argparse.Namespace) -> None:
    from app.web.migrations import apply_migrations
    from app.web.security import (
        hash_password,
        is_valid_email,
        new_token,
        normalize_email,
        password_problem,
        token_hash,
    )
    from app.web.store import WebStore

    settings = get_settings()
    pool = await _web_pool(settings)
    try:
        await apply_migrations(pool)
        store = WebStore(pool)
        action = args.web_command

        if action == "list":
            users = await store.list_users()
            payload = [
                {
                    "id": str(user["id"]),
                    "email": user["email"],
                    "role": user["role"],
                    "is_active": user["is_active"],
                    "created_at": user["created_at"].isoformat(),
                    "last_login": user["last_login"].isoformat() if user["last_login"] else None,
                }
                for user in users
            ]
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return

        email = normalize_email(args.email)
        if not is_valid_email(email):
            raise SystemExit("invalid email")
        user = await store.get_user_by_email(email)

        if action == "create":
            if user is not None:
                raise SystemExit("user already exists")
            if args.password_stdin:
                password = _read_password()
                problem = password_problem(password, settings.web_password_min_len)
                if problem:
                    raise SystemExit(problem)
                created = await store.create_user(
                    email,
                    role=args.role,
                    password_hash=hash_password(password),
                    is_active=True,
                )
                print(
                    json.dumps(
                        {"created": str(created["id"]), "email": email, "role": args.role},
                        ensure_ascii=False,
                    )
                )
                return
            token = new_token()
            invite = await store.create_invite(
                email,
                args.role,
                "invite",
                token_hash(token),
                None,
                datetime.now(UTC) + timedelta(days=settings.web_invite_ttl_days),
            )
            print(
                json.dumps(
                    {
                        "invite": f"{_web_base(settings)}/invite/{token}",
                        "email": email,
                        "role": args.role,
                        "expires_at": invite["expires_at"].isoformat(),
                    },
                    ensure_ascii=False,
                )
            )
            return

        if action in {"passwd", "invite"}:
            if user is None:
                raise SystemExit("user not found")
            if action == "passwd":
                password = _read_password()
                problem = password_problem(password, settings.web_password_min_len)
                if problem:
                    raise SystemExit(problem)
                await store.set_password(user["id"], hash_password(password))
                await store.revoke_user_sessions(user["id"])
                print(json.dumps({"password_updated": email}, ensure_ascii=False))
                return
            token = new_token()
            invite = await store.create_invite(
                email,
                user["role"],
                "reset",
                token_hash(token),
                None,
                datetime.now(UTC) + timedelta(days=settings.web_invite_ttl_days),
            )
            print(
                json.dumps(
                    {
                        "reset": f"{_web_base(settings)}/invite/{token}",
                        "email": email,
                        "expires_at": invite["expires_at"].isoformat(),
                    },
                    ensure_ascii=False,
                )
            )
            return
    finally:
        await pool.close()


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

    db = sub.add_parser("db", help="database maintenance")
    db_sub = db.add_subparsers(dest="db_command", required=True)
    db_migrate = db_sub.add_parser("migrate", help="apply web ui migrations")
    db_migrate.set_defaults(func=lambda args: asyncio.run(cmd_db_migrate(args)))

    web_user = sub.add_parser("web-user", help="manage web ui users")
    web_sub = web_user.add_subparsers(dest="web_command", required=True)

    web_create = web_sub.add_parser("create", help="create a user or an invite link")
    web_create.add_argument("--email", required=True)
    web_create.add_argument("--role", choices=["user", "admin"], default="user")
    web_create.add_argument(
        "--password-stdin",
        action="store_true",
        help="read the password from stdin/tty instead of printing an invite link",
    )
    web_create.set_defaults(func=lambda args: asyncio.run(cmd_web_user(args)))

    web_list = web_sub.add_parser("list", help="list web users")
    web_list.set_defaults(func=lambda args: asyncio.run(cmd_web_user(args)))

    web_passwd = web_sub.add_parser("passwd", help="set a password and revoke sessions")
    web_passwd.add_argument("--email", required=True)
    web_passwd.set_defaults(func=lambda args: asyncio.run(cmd_web_user(args)))

    web_invite = web_sub.add_parser("invite", help="issue a one-time password reset link")
    web_invite.add_argument("--email", required=True)
    web_invite.set_defaults(func=lambda args: asyncio.run(cmd_web_user(args)))

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
