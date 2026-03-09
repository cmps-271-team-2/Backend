from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Any
from uuid import uuid4


Vector = list[float]
Metadata = dict[str, Any]


@dataclass(slots=True)
class SemanticRecord:
    id: str
    vector: Vector
    metadata: Metadata


@dataclass(slots=True)
class SemanticQueryResult:
    id: str
    score: float
    metadata: Metadata


_singleton: "SemanticService | None" = None


def get_semantic_service() -> "SemanticService":
    global _singleton
    if _singleton is None:
        _singleton = SemanticService()
    return _singleton


class SemanticService:
    """Mock in-memory vector store for semantic search experiments."""

    def __init__(self) -> None:
        self._records: dict[str, SemanticRecord] = {}
        self._vector_size: int | None = None

    def upsert(self, vector: Vector, metadata: Metadata, item_id: str | None = None) -> str:
        self._validate_vector(vector)
        record_id = item_id or str(uuid4())
        self._records[record_id] = SemanticRecord(
            id=record_id,
            vector=list(vector),
            metadata=dict(metadata),
        )
        return record_id

    def upsert_many(self, items: list[tuple[Vector, Metadata, str | None]]) -> list[str]:
        ids: list[str] = []
        for vector, metadata, item_id in items:
            ids.append(self.upsert(vector=vector, metadata=metadata, item_id=item_id))
        return ids

    def query(self, vector: Vector, top_k: int = 20) -> list[SemanticQueryResult]:
        self._validate_vector(vector)
        if top_k <= 0:
            return []

        query_vector = list(vector)
        ranked = sorted(
            (
                SemanticQueryResult(
                    id=record.id,
                    score=_cosine_similarity(query_vector, record.vector),
                    metadata=dict(record.metadata),
                )
                for record in self._records.values()
            ),
            key=lambda result: result.score,
            reverse=True,
        )
        return ranked[:top_k]

    def query_text(self, query_text: str, top_k: int = 20) -> list[SemanticQueryResult]:
        from app.services.openai_service import get_openai_service

        query_vector = get_openai_service().get_embedding(query_text)
        return self.query(query_vector, top_k=top_k)

    def query_posts(self, query_text: str, top_k: int = 20) -> list[Metadata]:
        limit = max(0, min(top_k, 20))
        matches: list[Metadata] = []
        for result in self.query_text(query_text, top_k=limit):
            post = dict(result.metadata.get("post") or {})
            post["id"] = result.metadata.get("postId", result.id)
            post["score"] = result.score

            course_id = result.metadata.get("courseId")
            if course_id is not None:
                post["courseId"] = course_id

            course = result.metadata.get("course")
            if course is not None:
                post["course"] = course

            matches.append(post)
        return matches

    def delete(self, item_id: str) -> bool:
        return self._records.pop(item_id, None) is not None

    def clear(self) -> None:
        self._records.clear()
        self._vector_size = None

    def count(self) -> int:
        return len(self._records)

    def _validate_vector(self, vector: Vector) -> None:
        if not vector:
            raise ValueError("Vector must not be empty.")

        if self._vector_size is None:
            self._vector_size = len(vector)
            return

        if len(vector) != self._vector_size:
            raise ValueError(
                f"Expected vector size {self._vector_size}, got {len(vector)}."
            )


def _cosine_similarity(left: Vector, right: Vector) -> float:
    left_norm = sqrt(sum(value * value for value in left))
    right_norm = sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0

    dot_product = sum(left_value * right_value for left_value, right_value in zip(left, right))
    return dot_product / (left_norm * right_norm)