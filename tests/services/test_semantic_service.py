from __future__ import annotations

from typing import Any, cast

import pytest

from app.services import semantic_service as semantic


class FakeListIndexes:
    def __init__(self, names):
        self._names = names

    def names(self):
        return list(self._names)


class FakeMatch:
    def __init__(self, match_id: str, score: float, metadata: dict):
        self.id = match_id
        self.score = score
        self.metadata = metadata


class FakeQueryResponse:
    def __init__(self, matches):
        self.matches = matches


class FakeIndex:
    def __init__(self):
        self.upserts = []
        self.deleted = []
        self._stats = {"total_vector_count": 3, "namespaces": {"ns": {"vector_count": 2}}}

    def upsert(self, vectors, namespace=None):
        self.upserts.append((vectors, namespace))

    def query(self, vector, top_k, include_metadata, namespace=None):
        return FakeQueryResponse([
            FakeMatch("a", 0.9, {"postId": "post-1", "post": {"text": "hello"}}),
        ])

    def delete(self, ids=None, delete_all=False, namespace=None):
        self.deleted.append({"ids": ids, "delete_all": delete_all, "namespace": namespace})

    def describe_index_stats(self):
        return self._stats


class FakePinecone:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.index = FakeIndex()
        self.created = []

    def list_indexes(self):
        return FakeListIndexes(["unitok-test"])

    def create_index(self, name, dimension, metric, spec):
        self.created.append((name, dimension, metric, spec))

    def Index(self, _name):
        return self.index


def _make_vector():
    return [0.01] * semantic.EMBEDDING_DIMENSION


def test_semantic_service_requires_api_key(monkeypatch):
    monkeypatch.delenv("PINECONE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="PINECONE_API_KEY"):
        semantic.SemanticService()


def test_semantic_service_core_paths(monkeypatch):
    monkeypatch.setenv("PINECONE_API_KEY", "pc-key")
    monkeypatch.setenv("PINECONE_INDEX_NAME", "unitok-test")
    monkeypatch.setenv("PINECONE_NAMESPACE", "ns")
    monkeypatch.setattr(semantic, "Pinecone", FakePinecone)

    service = semantic.SemanticService()
    monkeypatch.setattr(
        service,
        "query_text",
        lambda query_text, top_k=20: [
            semantic.SemanticQueryResult(
                id="item-1",
                score=0.8,
                metadata={"postId": "post-1", "post": {"text": "hello"}},
            )
        ],
    )
    item_id = service.upsert(_make_vector(), {"post": {"text": "x"}}, item_id="item-1")
    results = service.query(_make_vector(), top_k=3)
    posts = service.query_posts("query", top_k=5)
    deleted = service.delete("item-1")
    count = service.count()

    assert item_id == "item-1"
    assert results[0].id == "a"
    assert posts[0]["id"] == "post-1"
    assert deleted is True
    assert count == 2


def test_semantic_service_vector_validation(monkeypatch):
    monkeypatch.setenv("PINECONE_API_KEY", "pc-key")
    monkeypatch.setenv("PINECONE_INDEX_NAME", "unitok-test")
    monkeypatch.delenv("PINECONE_NAMESPACE", raising=False)
    monkeypatch.setattr(semantic, "Pinecone", FakePinecone)

    service = semantic.SemanticService()
    with pytest.raises(ValueError, match="must not be empty"):
        service.query([])


def test_semantic_service_ignores_forbidden_default_namespace(monkeypatch):
    monkeypatch.setenv("PINECONE_API_KEY", "pc-key")
    monkeypatch.setenv("PINECONE_INDEX_NAME", "unitok-test")
    monkeypatch.setenv("PINECONE_NAMESPACE", "__default__")
    monkeypatch.setattr(semantic, "Pinecone", FakePinecone)

    service = semantic.SemanticService()
    service.upsert(_make_vector(), {"post": {"text": "x"}}, item_id="item-1")

    service_any = cast(Any, service)
    assert service_any._namespace is None
    assert service_any._index.upserts[0][1] is None


def test_metadata_encode_decode_roundtrip():
    encoded = semantic._encode_metadata({"k": {"a": 1}, "tags": ["x", "y"]})
    decoded = semantic._decode_metadata(encoded)
    assert decoded["k"]["a"] == 1
    assert decoded["tags"] == ["x", "y"]
