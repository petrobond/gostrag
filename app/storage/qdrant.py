from __future__ import annotations

from dataclasses import dataclass

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qm


@dataclass(slots=True)
class DenseHit:
    chunk_id: str
    score: float
    payload: dict


class QdrantStore:
    def __init__(self, url: str, collection: str) -> None:
        self.client = AsyncQdrantClient(url=url)
        self.collection = collection

    async def ensure_collection(self, dim: int) -> None:
        exists = await self.client.collection_exists(self.collection)
        if exists:
            return
        await self.client.create_collection(
            collection_name=self.collection,
            vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE),
        )
        for field in ("doc_id", "gost_number", "section", "table_number"):
            await self.client.create_payload_index(
                collection_name=self.collection,
                field_name=field,
                field_schema=qm.PayloadSchemaType.KEYWORD,
            )

    async def upsert(self, points: list[qm.PointStruct], batch_size: int = 64) -> None:
        for start in range(0, len(points), batch_size):
            await self.client.upsert(
                collection_name=self.collection,
                points=points[start : start + batch_size],
                wait=True,
            )

    async def search(
        self,
        vector: list[float],
        limit: int = 20,
        gost_number: str | None = None,
        table_number: str | None = None,
    ) -> list[DenseHit]:
        conditions = []
        if gost_number:
            conditions.append(
                qm.FieldCondition(key="gost_number", match=qm.MatchValue(value=gost_number))
            )
        if table_number:
            conditions.append(
                qm.FieldCondition(key="table_number", match=qm.MatchValue(value=table_number))
            )
        query_filter = qm.Filter(must=conditions) if conditions else None
        response = await self.client.query_points(
            collection_name=self.collection,
            query=vector,
            limit=limit,
            query_filter=query_filter,
            with_payload=True,
        )
        hits: list[DenseHit] = []
        for point in response.points:
            payload = point.payload or {}
            # Point id is a UUID; chunk lookups must use the corpus chunk_id from payload.
            chunk_id = str(payload.get("chunk_id") or point.id)
            hits.append(DenseHit(chunk_id=chunk_id, score=float(point.score), payload=payload))
        return hits

    async def close(self) -> None:
        await self.client.close()
