from __future__ import annotations

import pickle
import re
from dataclasses import dataclass
from pathlib import Path

import pymorphy3
from rank_bm25 import BM25Okapi

TOKEN_RE = re.compile(r"[а-яёa-z0-9]+", re.IGNORECASE)


@dataclass(slots=True)
class BM25Hit:
    chunk_id: str
    score: float
    index: int


class BM25Index:
    """Russian-aware BM25 over chunk texts."""

    def __init__(self, chunk_ids: list[str], texts: list[str]) -> None:
        self.chunk_ids = chunk_ids
        self._morph = pymorphy3.MorphAnalyzer()
        tokenized = [self.tokenize(text) for text in texts]
        self._bm25 = BM25Okapi(tokenized)

    def tokenize(self, text: str) -> list[str]:
        return [self._morph.parse(token)[0].normal_form for token in TOKEN_RE.findall(text.lower())]

    def search(self, query: str, top_k: int = 20) -> list[BM25Hit]:
        tokens = self.tokenize(query)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)[:top_k]
        return [
            BM25Hit(chunk_id=self.chunk_ids[idx], score=float(score), index=idx)
            for idx, score in ranked
            if score > 0
        ]

    def save(self, path: Path) -> None:
        with path.open("wb") as fh:
            pickle.dump(self, fh)

    @classmethod
    def load(cls, path: Path) -> BM25Index:
        with path.open("rb") as fh:
            return pickle.load(fh)
