from __future__ import annotations


def rrf(rankings: list[list[str]], k: int = 60, top_n: int = 10) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion over several ranked lists of chunk ids."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_n]
