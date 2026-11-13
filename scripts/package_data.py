"""Package corpus, index and KB into a versioned data artefact."""

from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.audit.version import get_git_commit


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", default="data/corpus")
    parser.add_argument("--index", default="data/index")
    parser.add_argument("--kb", default="data/kb")
    parser.add_argument("--source", default="")
    parser.add_argument("--out", default="dist")
    parser.add_argument("--version", default="")
    args = parser.parse_args()

    corpus = Path(args.corpus)
    index = Path(args.index)
    kb = Path(args.kb)
    source = Path(args.source) if args.source else None
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    quality = json.loads((corpus / "quality_report.json").read_text(encoding="utf-8"))
    version = args.version or str(quality.get("corpus_version") or "unknown")
    archive = out / f"data-{version}.tar.gz"

    with tarfile.open(archive, "w:gz") as tar:
        for path, arcname in ((corpus, "corpus"), (index, "index"), (kb, "kb")):
            if path.exists():
                tar.add(path, arcname=arcname)
        if source is not None and source.exists():
            tar.add(source, arcname="source")

    chunks = [
        json.loads(line)
        for line in (corpus / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    embed_report = {}
    if (index / "embed_report.json").exists():
        embed_report = json.loads((index / "embed_report.json").read_text(encoding="utf-8"))

    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "corpus_version": version,
        "git_commit": get_git_commit(),
        "archive": archive.name,
        "archive_sha256": sha256(archive),
        "archive_size": archive.stat().st_size,
        "counts": {
            "documents": len(
                json.loads((corpus / "documents.json").read_text(encoding="utf-8"))
            ),
            "chunks": len(chunks),
            "table_chunks": sum(1 for row in chunks if row.get("chunk_type") == "table"),
            "unique_text_hash": len({row["text_hash"] for row in chunks}),
            "unique_uuid5": len(
                {str(uuid.uuid5(uuid.NAMESPACE_URL, row["chunk_id"])) for row in chunks}
            ),
        },
        "embedding": {
            "provider": embed_report.get("embedding_provider"),
            "model": embed_report.get("embedding_model"),
            "dim": embed_report.get("embedding_dim"),
            "collection": embed_report.get("collection"),
        },
        "files": [
            {"path": str(path), "sha256": sha256(path)}
            for path in sorted(corpus.glob("*"))
            if path.is_file()
        ],
    }
    manifest_path = out / f"manifest-{version}.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"archive": str(archive), "manifest": str(manifest_path)}, indent=2))


if __name__ == "__main__":
    main()
