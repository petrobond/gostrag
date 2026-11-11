from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

import httpx
import structlog

from app.config import Settings

log = structlog.get_logger()


class GigaChatError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"GigaChat HTTP {status}: {message}")
        self.status = status
        self.message = message


@dataclass(slots=True)
class ChatResult:
    content: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0


class GigaChatClient:
    """Minimal async client for GigaChat REST API."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._token: str = ""
        self._expires_at: float = 0.0

    async def _get_token(self) -> str:
        if self._token and time.time() < self._expires_at - 120:
            return self._token
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": str(uuid.uuid4()),
            "Authorization": f"Basic {self.settings.gigachat_credentials}",
        }
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            response = await client.post(
                self.settings.gigachat_auth_url,
                headers=headers,
                data={"scope": self.settings.gigachat_scope},
            )
        if response.status_code != 200:
            raise GigaChatError(response.status_code, response.text[:500])
        data = response.json()
        self._token = data["access_token"]
        self._expires_at = float(data.get("expires_at", 0)) / 1000 or (time.time() + 1800)
        log.info("gigachat_token_refreshed", expires_at=self._expires_at)
        return self._token

    async def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {await self._get_token()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def models(self) -> list[dict]:
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            response = await client.get(
                f"{self.settings.gigachat_base_url}/models", headers=await self._headers()
            )
        response.raise_for_status()
        return response.json().get("data", [])

    async def chat(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.1,
        max_tokens: int = 1200,
    ) -> ChatResult:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        async with httpx.AsyncClient(verify=False, timeout=self.settings.request_timeout_sec) as client:
            response = await client.post(
                f"{self.settings.gigachat_base_url}/chat/completions",
                headers=await self._headers(),
                json=payload,
            )
        if response.status_code != 200:
            raise GigaChatError(response.status_code, response.text[:500])
        data = response.json()
        choice = data["choices"][0]["message"]
        usage = data.get("usage", {})
        return ChatResult(
            content=choice.get("content", ""),
            model=data.get("model", model),
            tokens_in=int(usage.get("prompt_tokens", 0)),
            tokens_out=int(usage.get("completion_tokens", 0)),
        )

    async def embeddings(self, model: str, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(verify=False, timeout=self.settings.request_timeout_sec) as client:
            response = await client.post(
                f"{self.settings.gigachat_base_url}/embeddings",
                headers=await self._headers(),
                json={"model": model, "input": texts},
            )
        if response.status_code != 200:
            raise GigaChatError(response.status_code, response.text[:500])
        data = response.json()
        return [item["embedding"] for item in data["data"]]
