"""Upload a data artefact and its manifest to S3."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import boto3

from app.config import get_settings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--prefix", default="data")
    args = parser.parse_args()

    archive = Path(args.archive)
    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    version = manifest["corpus_version"]
    settings = get_settings()
    if not settings.s3_bucket:
        raise SystemExit("S3_BUCKET is not configured")

    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    )
    base = f"{args.prefix.strip('/')}/{version}"
    archive_key = f"{base}/{archive.name}"
    manifest_key = f"{base}/{manifest_path.name}"
    client.upload_file(str(archive), settings.s3_bucket, archive_key)
    client.upload_file(
        str(manifest_path),
        settings.s3_bucket,
        manifest_key,
        ExtraArgs={"ContentType": "application/json"},
    )
    print(f"s3://{settings.s3_bucket}/{archive_key}")
    print(f"s3://{settings.s3_bucket}/{manifest_key}")


if __name__ == "__main__":
    main()
