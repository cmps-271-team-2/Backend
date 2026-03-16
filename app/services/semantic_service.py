from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec


load_dotenv()


Vector = list[float]
Metadata = dict[str, Any]
EMBEDDING_DIMENSION = int(os.getenv("PINECONE_VECTOR_DIMENSION", "1024"))


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
    """Pinecone-backed vector store for semantic post search."""

    def __init__(self) -> None:
        api_key = os.getenv("PINECONE_API_KEY")
        if not api_key:
            raise ValueError("PINECONE_API_KEY not set in environment.")

        self._index_name = os.getenv("PINECONE_INDEX_NAME", "unitok-posts")
        self._namespace = _normalize_namespace(os.getenv("PINECONE_NAMESPACE"))
        self._cloud = os.getenv("PINECONE_CLOUD", "aws")
        self._region = os.getenv("PINECONE_REGION", "us-east-1")

        self._client = Pinecone(api_key=api_key)
        self._ensure_index()
        self._index = self._client.Index(self._index_name)

    def upsert(self, vector: Vector, metadata: Metadata, item_id: str | None = None) -> str:
        self._validate_vector(vector)
        record_id = item_id or str(uuid4())
        payload = [
            {
                "id": record_id,
                "values": list(vector),
                "metadata": _encode_metadata(metadata),
            }
        ]
        if self._namespace:
            self._index.upsert(vectors=payload, namespace=self._namespace)
        else:
            self._index.upsert(vectors=payload)
        return record_id

    def upsert_many(self, items: list[tuple[Vector, Metadata, str | None]]) -> list[str]:
        ids: list[str] = []
        vectors: list[dict[str, Any]] = []
        for vector, metadata, item_id in items:
            self._validate_vector(vector)
            record_id = item_id or str(uuid4())
            ids.append(record_id)
            vectors.append(
                {
                    "id": record_id,
                    "values": list(vector),
                    "metadata": _encode_metadata(metadata),
                }
            )

        if vectors:
            if self._namespace:
                self._index.upsert(vectors=vectors, namespace=self._namespace)
            else:
                self._index.upsert(vectors=vectors)
        return ids

    def query(self, vector: Vector, top_k: int = 20) -> list[SemanticQueryResult]:
        self._validate_vector(vector)
        if top_k <= 0:
            return []

        if self._namespace:
            response = self._index.query(
                vector=list(vector),
                top_k=top_k,
                include_metadata=True,
                namespace=self._namespace,
            )
        else:
            response = self._index.query(
                vector=list(vector),
                top_k=top_k,
                include_metadata=True,
            )

        matches = list(getattr(response, "matches", []) or [])

        results: list[SemanticQueryResult] = []
        for match in matches:
            metadata = getattr(match, "metadata", {}) or {}
            match_id = getattr(match, "id", "")
            score = getattr(match, "score", 0.0)

            results.append(
                SemanticQueryResult(
                    id=str(match_id or ""),
                    score=float(score or 0.0),
                    metadata=_decode_metadata(metadata or {}),
                )
            )

        return results

    def query_text(self, query_text: str, top_k: int = 20) -> list[SemanticQueryResult]:
        query_vector = self.embed_text(query_text)
        return self.query(query_vector, top_k=top_k)

    def embed_text(self, text: str) -> Vector:
        return _embed_text(text, dimension=EMBEDDING_DIMENSION)

    def embed_texts(self, texts: list[str]) -> list[Vector]:
        return [_embed_text(text, dimension=EMBEDDING_DIMENSION) for text in texts]

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
        if not item_id:
            return False

        if self._namespace:
            self._index.delete(ids=[item_id], namespace=self._namespace)
        else:
            self._index.delete(ids=[item_id])
        return True

    def clear(self) -> None:
        if self._namespace:
            self._index.delete(delete_all=True, namespace=self._namespace)
        else:
            self._index.delete(delete_all=True)

    def count(self) -> int:
        stats = self._index.describe_index_stats()
        if self._namespace:
            namespaces = getattr(stats, "namespaces", None)
            if namespaces is None and isinstance(stats, dict):
                namespaces = stats.get("namespaces", {})

            namespace_stats = (namespaces or {}).get(self._namespace, {})
            vector_count = getattr(namespace_stats, "vector_count", None)
            if vector_count is None and isinstance(namespace_stats, dict):
                vector_count = namespace_stats.get("vector_count", 0)
            return int(vector_count or 0)

        total_count = getattr(stats, "total_vector_count", None)
        if total_count is None and isinstance(stats, dict):
            total_count = stats.get("total_vector_count", 0)
        return int(total_count or 0)

    def _validate_vector(self, vector: Vector) -> None:
        if not vector:
            raise ValueError("Vector must not be empty.")

        if len(vector) != EMBEDDING_DIMENSION:
            raise ValueError(
                f"Expected vector size {EMBEDDING_DIMENSION}, got {len(vector)}."
            )

    def _ensure_index(self) -> None:
        existing_indexes = self._client.list_indexes().names()
        if self._index_name in existing_indexes:
            return

        self._client.create_index(
            name=self._index_name,
            dimension=EMBEDDING_DIMENSION,
            metric="cosine",
            spec=ServerlessSpec(cloud=self._cloud, region=self._region),
        )

def _encode_metadata(metadata: Metadata) -> dict[str, Any]:
    encoded: dict[str, Any] = {}
    for key, value in metadata.items():
        normalized = _normalize_metadata_value(value)
        if normalized is None:
            continue

        if _is_supported_metadata_value(normalized):
            encoded[key] = normalized
            continue

        encoded[f"{key}Json"] = json.dumps(normalized, separators=(",", ":"), ensure_ascii=True)

    return encoded


def _decode_metadata(metadata: dict[str, Any]) -> Metadata:
    decoded: Metadata = {}
    for key, value in metadata.items():
        if key.endswith("Json") and isinstance(value, str):
            decoded_key = key[:-4]
            try:
                decoded[decoded_key] = json.loads(value)
            except json.JSONDecodeError:
                decoded[decoded_key] = value
            continue

        decoded[key] = value

    return decoded


def _normalize_metadata_value(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, inner_value in value.items():
            normalized_value = _normalize_metadata_value(inner_value)
            if normalized_value is not None:
                normalized[str(key)] = normalized_value
        return normalized

    if isinstance(value, list):
        normalized_items = [_normalize_metadata_value(item) for item in value]
        return [item for item in normalized_items if item is not None]

    return str(value)


def _is_supported_metadata_value(value: Any) -> bool:
    if isinstance(value, (str, int, float, bool)):
        return True

    if isinstance(value, list):
        return all(isinstance(item, str) for item in value)

    return False


def _normalize_namespace(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.strip()
    if not normalized:
        return None

    if normalized == "__default__":
        return None

    return normalized


_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def _embed_text(text: str, dimension: int) -> Vector:
    if dimension <= 0:
        raise ValueError("PINECONE_VECTOR_DIMENSION must be greater than zero.")

    normalized = (text or "").lower()
    tokens = _TOKEN_PATTERN.findall(normalized)
    if not tokens:
        tokens = ["_empty_"]

    vector = [0.0] * dimension
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimension
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        magnitude = 1.0 + (int.from_bytes(digest[5:7], "big") / 65535.0)
        vector[index] += sign * magnitude

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]