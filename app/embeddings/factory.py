from __future__ import annotations

from app.config import Settings
from app.embeddings.base import Embedder


def get_embedder(settings: Settings) -> Embedder:
    provider = settings.embedding_provider.lower()
    if provider == "gigachat":
        from app.embeddings.gigachat import GigaChatEmbedder

        return GigaChatEmbedder(settings)
    from app.embeddings.local_e5 import LocalE5Embedder

    return LocalE5Embedder(
        cache_dir=settings.embedding_cache_dir,
        threads=settings.embedding_threads or None,
    )
