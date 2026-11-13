from __future__ import annotations

from app.config import Settings
from app.embeddings.base import Embedder


def get_embedder(settings: Settings) -> Embedder:
    provider = settings.embedding_provider.lower()
    if provider == "cloudru":
        from app.embeddings.cloudru import CloudRuEmbedder

        return CloudRuEmbedder(settings)
    if provider == "gigachat":
        from app.embeddings.gigachat import GigaChatEmbedder

        return GigaChatEmbedder(settings)
    try:
        from app.embeddings.local_e5 import LocalE5Embedder
    except ImportError as exc:
        raise RuntimeError(
            "local embeddings are not installed: use EMBEDDING_PROVIDER=cloudru "
            "or install gostrag[local]"
        ) from exc

    return LocalE5Embedder(
        cache_dir=settings.embedding_cache_dir,
        threads=settings.embedding_threads or None,
    )
