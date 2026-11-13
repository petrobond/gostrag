"""Create, download and restore Qdrant collection snapshots."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import httpx


def _base(url: str) -> str:
    return url.rstrip("/")


def cmd_list(args: argparse.Namespace) -> None:
    response = httpx.get(
        f"{_base(args.url)}/collections/{args.collection}/snapshots", timeout=60
    )
    response.raise_for_status()
    for item in response.json().get("result", []):
        print(f"{item['name']}\t{item['size']}\t{item['creation_time']}")


def cmd_download(args: argparse.Namespace) -> None:
    response = httpx.post(
        f"{_base(args.url)}/collections/{args.collection}/snapshots", timeout=300
    )
    response.raise_for_status()
    name = response.json()["result"]["name"]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with httpx.stream(
        "GET",
        f"{_base(args.url)}/collections/{args.collection}/snapshots/{name}",
        timeout=300,
    ) as stream:
        stream.raise_for_status()
        with out.open("wb") as fh:
            for block in stream.iter_bytes():
                fh.write(block)
                digest.update(block)
    print(f"{out} {out.stat().st_size} {digest.hexdigest()}")


def cmd_restore(args: argparse.Namespace) -> None:
    path = Path(args.file)
    if not path.exists():
        raise SystemExit(f"snapshot not found: {path}")
    url = (
        f"{_base(args.url)}/collections/{args.collection}/snapshots/upload"
        "?priority=snapshot"
    )
    with path.open("rb") as fh:
        response = httpx.post(
            url,
            files={"snapshot": (path.name, fh, "application/octet-stream")},
            timeout=600,
        )
    if response.status_code >= 400:
        raise SystemExit(f"restore failed: {response.status_code} {response.text[:500]}")
    print(response.text[:1000])


def main() -> None:
    parser = argparse.ArgumentParser(prog="qdrant_snapshot")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--url", default="http://localhost:6333")
    common.add_argument("--collection", default="gost_chunks_bge_m3")
    sub = parser.add_subparsers(dest="command", required=True)

    listed = sub.add_parser("list", parents=[common])
    listed.set_defaults(func=cmd_list)

    download = sub.add_parser("download", parents=[common])
    download.add_argument("--out", required=True)
    download.set_defaults(func=cmd_download)

    restore = sub.add_parser("restore", parents=[common])
    restore.add_argument("--file", required=True)
    restore.set_defaults(func=cmd_restore)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
