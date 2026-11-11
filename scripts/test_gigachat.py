"""Check GigaChat credentials, models and a tiny chat/embedding call."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.llm.gigachat import GigaChatClient  # noqa: E402


async def main() -> None:
    settings = get_settings()
    client = GigaChatClient(settings)
    models = await client.models()
    print("models:", [m.get("id") for m in models][:20])

    result = await client.chat(
        settings.gigachat_model_ultra,
        [{"role": "user", "content": "Ответь одним словом: работает?"}],
        max_tokens=20,
    )
    print("chat:", result.model, repr(result.content[:100]), result.tokens_in, result.tokens_out)

    vectors = await client.embeddings(settings.gigachat_embedding_model, ["проверка эмбеддингов"])
    print("embedding dim:", len(vectors[0]))


if __name__ == "__main__":
    asyncio.run(main())
