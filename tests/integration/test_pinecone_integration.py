from __future__ import annotations

import os
import time
from typing import Any, cast
from uuid import uuid4

import pytest
from dotenv import load_dotenv
from pinecone import Pinecone


load_dotenv()


def _extract_match_ids(search_response: object) -> list[str]:
    ids: list[str] = []

    if isinstance(search_response, dict):
        hits = (
            search_response.get("hits")
            or ((search_response.get("result") or {}).get("hits") if isinstance(search_response.get("result"), dict) else None)
            or search_response.get("matches")
            or []
        )
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            hit_id = hit.get("id") or hit.get("_id")
            if isinstance(hit_id, str) and hit_id:
                ids.append(hit_id)
        return ids

    matches = getattr(search_response, "matches", None) or []
    for match in matches:
        match_id = getattr(match, "id", "")
        if isinstance(match_id, str) and match_id:
            ids.append(match_id)

    return ids


def _extract_embedding_values(embed_response: object) -> list[list[float]]:
    vectors: list[list[float]] = []

    if isinstance(embed_response, dict):
        data = embed_response.get("data") or []
        for item in data:
            if not isinstance(item, dict):
                continue
            values = item.get("values")
            if isinstance(values, list) and values:
                vectors.append([float(v) for v in values])
        return vectors

    data = getattr(embed_response, "data", None) or []
    for item in data:
        values = getattr(item, "values", None)
        if isinstance(values, list) and values:
            vectors.append([float(v) for v in values])

    return vectors


def _namespace_not_allowed(exc: Exception, namespace: str) -> bool:
    if namespace != "__default__":
        return False
    return "namespace='__default__' is not allowed" in str(exc)


def _upsert_records_with_namespace_fallback(index: object, namespace: str, records: list[dict[str, object]]) -> bool:
    try:
        getattr(index, "upsert_records")(namespace=namespace, records=records)
        return True
    except Exception as exc:
        if _namespace_not_allowed(exc, namespace):
            getattr(index, "upsert_records")(records=records)
            return True
        raise


def _search_with_namespace_fallback(index: object, namespace: str, query: dict[str, object]) -> object:
    try:
        return getattr(index, "search")(namespace=namespace, query=query)
    except Exception as exc:
        if _namespace_not_allowed(exc, namespace):
            return getattr(index, "search")(query=query)
        raise


def _upsert_vectors_with_namespace_fallback(index: object, namespace: str, vectors: list[dict[str, object]]) -> None:
    try:
        getattr(index, "upsert")(vectors=vectors, namespace=namespace)
    except Exception as exc:
        if _namespace_not_allowed(exc, namespace):
            getattr(index, "upsert")(vectors=vectors)
            return
        raise


def _query_with_namespace_fallback(index: object, namespace: str, vector: list[float]) -> object:
    try:
        return getattr(index, "query")(
            vector=vector,
            top_k=3,
            include_metadata=True,
            namespace=namespace,
        )
    except Exception as exc:
        if _namespace_not_allowed(exc, namespace):
            return getattr(index, "query")(
                vector=vector,
                top_k=3,
                include_metadata=True,
            )
        raise


def _delete_with_namespace_fallback(index: object, namespace: str, ids: list[str]) -> None:
    try:
        getattr(index, "delete")(ids=ids, namespace=namespace)
    except Exception as exc:
        if _namespace_not_allowed(exc, namespace):
            getattr(index, "delete")(ids=ids)
            return
        raise


@pytest.mark.integration
def test_pinecone_integrated_embedding_text_roundtrip():
    api_key = os.getenv("PINECONE_API_KEY")
    index_name = os.getenv("PINECONE_INDEX_NAME")
    namespace = os.getenv("PINECONE_NAMESPACE", "__default__")

    if not api_key or not index_name:
        pytest.skip("Pinecone integration test skipped: PINECONE_API_KEY/PINECONE_INDEX_NAME missing.")

    pc = Pinecone(api_key=api_key)
    index = pc.Index(index_name)

    token = uuid4().hex[:12]
    tech_id = f"it-tech-{token}"
    food_id = f"it-food-{token}"

    records: list[dict[str, object]] = [
        {
            "id": tech_id,
            "text": f"Apple builds iPhone products and software platform {token}",
            "topic": "tech",
        },
        {
            "id": food_id,
            "text": f"Fresh apples are sweet fruits and healthy snacks {token}",
            "topic": "food",
        },
    ]

    try:
        used_text_api = False
        vectors: list[list[float]] = []
        try:
            used_text_api = _upsert_records_with_namespace_fallback(
                index=index,
                namespace=namespace,
                records=records,
            )
        except Exception as exc:
            # Older SDK/index combinations may not expose text APIs;
            # fallback to Pinecone inference embeddings + vector upsert/query.
            used_text_api = False

        if not used_text_api:
            model_name = os.getenv("PINECONE_EMBEDDING_MODEL", "llama-text-embed-v2")
            try:
                embed_response = cast(Any, pc).inference.embed(
                    model=model_name,
                    inputs=[
                        str(records[0]["text"]),
                        str(records[1]["text"]),
                        f"tech company apple iphone {token}",
                    ],
                    parameters={"input_type": "passage", "truncate": "END"},
                )
            except Exception as exc:
                pytest.skip(
                    "Pinecone inference embedding unavailable for this project/plan/index: "
                    f"{exc}"
                )

            vectors = _extract_embedding_values(embed_response)
            if len(vectors) < 3:
                pytest.skip("Pinecone inference did not return embeddings in expected format.")

            try:
                _upsert_vectors_with_namespace_fallback(
                    index=index,
                    namespace=namespace,
                    vectors=[
                        {"id": tech_id, "values": vectors[0], "metadata": {"topic": "tech", "token": token}},
                        {"id": food_id, "values": vectors[1], "metadata": {"topic": "food", "token": token}},
                    ],
                )
            except Exception as exc:
                if "Vector dimension" in str(exc):
                    pytest.skip(
                        "Pinecone inference model output dimension does not match index dimension. "
                        "Set PINECONE_EMBEDDING_MODEL to a compatible model for this index."
                    )
                raise

        found = False
        for _ in range(8):
            if used_text_api:
                response = _search_with_namespace_fallback(
                    index=index,
                    namespace=namespace,
                    query={
                        "inputs": {"text": f"tech company apple iphone {token}"},
                        "top_k": 3,
                    },
                )
            else:
                response = _query_with_namespace_fallback(
                    index=index,
                    namespace=namespace,
                    vector=vectors[2],
                )
            ids = _extract_match_ids(response)
            if tech_id in ids:
                found = True
                break
            time.sleep(1.5)

        assert found, "Expected tech record to be returned from Pinecone integrated text search."
    finally:
        try:
            _delete_with_namespace_fallback(index=index, namespace=namespace, ids=[tech_id, food_id])
        except Exception:
            pass