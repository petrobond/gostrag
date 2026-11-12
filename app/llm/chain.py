from __future__ import annotations

from dataclasses import dataclass

import httpx
import structlog

from app.config import Settings
from app.llm.gigachat import ChatResult, GigaChatClient, GigaChatError

log = structlog.get_logger()


@dataclass(slots=True)
class LLMResult:
    content: str
    model: str
    provider: str
    tokens_in: int = 0
    tokens_out: int = 0


class DeepSeekClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def chat(self, model: str, messages: list[dict], max_tokens: int, temperature: float = 0.1) -> ChatResult:
        if not self.settings.deepseek_api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not configured")
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_sec) as client:
            response = await client.post(
                f"{self.settings.deepseek_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.deepseek_api_key}"},
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
            )
        if response.status_code != 200:
            raise GigaChatError(response.status_code, response.text[:300])
        data = response.json()
        usage = data.get("usage", {})
        return ChatResult(
            content=data["choices"][0]["message"]["content"],
            model=data.get("model", model),
            tokens_in=int(usage.get("prompt_tokens", 0)),
            tokens_out=int(usage.get("completion_tokens", 0)),
        )


def classify(question: str) -> str:
    q = question.lower().strip()
    complex_markers = ("сравни", "проанализируй", "объясни", "почему", "какие требования", "в чём разница")
    simple_markers = ("что такое", "какой номер", "дай определение", "перечисли")
    if len(q) > 200 or sum(marker in q for marker in complex_markers) >= 1:
        return "complex"
    if len(q) < 120 or any(marker in q for marker in simple_markers):
        return "simple"
    return "medium"


class LLMChain:
    """GigaChat Ultra -> Max -> Pro -> Lite -> DeepSeek fallback."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.gigachat = GigaChatClient(settings)
        self.deepseek = DeepSeekClient(settings)

    def order(self, complexity: str) -> list[tuple[str, str]]:
        ultra = self.settings.gigachat_model_ultra
        max_model = self.settings.gigachat_model_max
        pro = self.settings.gigachat_model_pro
        lite = self.settings.gigachat_model_lite
        # Ultra is always first: quality matters more than token savings.
        chains = {
            "complex": [ultra, max_model, pro, lite],
            "medium": [ultra, pro, max_model, lite],
            "simple": [ultra, pro, max_model, lite],
        }
        models = [(name, "gigachat") for name in chains.get(complexity, chains["medium"])]
        models.append((self.settings.deepseek_model, "deepseek"))
        return models

    async def chat(
        self,
        messages: list[dict],
        complexity: str = "medium",
        max_tokens: int = 1200,
        temperature: float = 0.1,
    ) -> LLMResult:
        last_error: Exception | None = None
        for model, provider in self.order(complexity):
            try:
                if provider == "gigachat":
                    result = await self.gigachat.chat(
                        model, messages, max_tokens=max_tokens, temperature=temperature
                    )
                else:
                    result = await self.deepseek.chat(
                        model, messages, max_tokens=max_tokens, temperature=temperature
                    )
                return LLMResult(
                    content=result.content,
                    model=result.model,
                    provider=provider,
                    tokens_in=result.tokens_in,
                    tokens_out=result.tokens_out,
                )
            except GigaChatError as exc:
                log.warning(
                    "llm_error",
                    model=model,
                    provider=provider,
                    status=exc.status,
                    message=exc.message[:200],
                )
                if exc.status in (402, 413, 429, 500):
                    last_error = exc
                    continue
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue
        raise RuntimeError(f"all models failed: {last_error}")
