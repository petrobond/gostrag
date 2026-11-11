from __future__ import annotations

from urllib.parse import quote

import boto3
from botocore.client import Config

from app.config import Settings


class S3Store:
    """Presigned links to source PDFs with page anchors."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.bucket = settings.s3_bucket
        self.enabled = bool(settings.s3_bucket and settings.s3_access_key)
        self._keys: dict[str, str] = {}
        self.client = None
        if self.enabled:
            self.client = boto3.client(
                "s3",
                endpoint_url=settings.s3_endpoint,
                aws_access_key_id=settings.s3_access_key,
                aws_secret_access_key=settings.s3_secret_key,
                region_name=settings.s3_region,
                config=Config(signature_version="s3v4"),
            )
            self._build_index()

    def _build_index(self) -> None:
        prefix = self.settings.s3_prefix
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                key = item["Key"]
                if key.lower().endswith(".pdf"):
                    self._keys[key.rsplit("/", 1)[-1]] = key

    def url_for(self, filename: str, page: int, expires: int = 604800) -> str:
        if not self.enabled or filename not in self._keys:
            return ""
        url = self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": self._keys[filename]},
            ExpiresIn=expires,
        )
        anchor = f"#page={page}" if page else ""
        return f"{url}{anchor}"
