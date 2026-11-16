"""Request payload parsing (JSON or urlencoded) without extra dependencies."""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

from fastapi import HTTPException, Request

MAX_BODY_BYTES = 64 * 1024


async def read_payload(request: Request) -> dict[str, Any]:
    """Parse a JSON or form-urlencoded body once and cache it on the request."""
    cached = getattr(request.state, "payload", None)
    if cached is not None:
        return cached

    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="payload too large")

    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    data: dict[str, Any]
    if content_type == "application/json":
        try:
            parsed = json.loads(body or b"{}")
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="invalid json") from exc
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=400, detail="json object expected")
        data = parsed
    else:
        text = body.decode("utf-8", "replace")
        form = urllib.parse.parse_qs(text, keep_blank_values=True)
        data = {key: values[0] for key, values in form.items()}

    request.state.payload = data
    return data
