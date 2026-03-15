from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast

from dotenv import load_dotenv

from app.core.firebase_admin import init_firebase_admin
from app.core.firestore import get_db
from app.services.openai_service import get_openai_service
from app.services.semantic_service import get_semantic_service


INDEXING_VERSION = 1
TARGET_COLLECTIONS = {
	"course": "courses",
	"courses": "courses",
	"professor": "profiles",
	"profile": "profiles",
	"study-spot": "cafeterias",
	"food-spot": "cafeterias",
	"cafeteria": "cafeterias",
}


def update_posts_index() -> dict[str, int]:
	"""Rebuild the Pinecone semantic index from Firestore course posts."""
	load_dotenv()
	init_firebase_admin()

	db = get_db()
	openai_service = get_openai_service()
	semantic_service = get_semantic_service()
	semantic_service.clear()

	scanned = 0
	indexed = 0
	skipped_missing_target = 0
	skipped_missing_text = 0

	documents_to_index: list[tuple[Any, str, str, dict[str, Any]]] = []

	for post_snapshot in db.collection("posts").stream():
		scanned += 1
		candidate = _prepare_post_for_indexing(post_snapshot=post_snapshot, db=db)
		if candidate is None:
			post_data = post_snapshot.to_dict() or {}
			target_id = str(post_data.get("targetId") or post_data.get("targetid") or "").strip()
			document_text = _build_document_text(post_data, None)
			if not target_id:
				skipped_missing_target += 1
			else:
				skipped_missing_text += 1 if not document_text.strip() else 0
			continue

		documents_to_index.append(candidate)

	for post_reference, _, _, _ in documents_to_index:
		_set_post_index_status(post_reference, indexed=False)

	embeddings = openai_service.get_embeddings([document_text for _, _, document_text, _ in documents_to_index])

	for (post_reference, post_id, _, metadata), vector in zip(documents_to_index, embeddings):
		semantic_service.upsert(vector=vector, metadata=metadata, item_id=post_id)
		_set_post_index_status(post_reference, indexed=True)
		indexed += 1

	return {
		"scanned": scanned,
		"indexed": indexed,
		"skipped_missing_target": skipped_missing_target,
		"skipped_missing_text": skipped_missing_text,
	}


def upload_post(post_id: str) -> dict[str, Any]:
	"""Index a single Firestore post into the Pinecone semantic store."""
	load_dotenv()
	init_firebase_admin()

	db = get_db()
	semantic_service = get_semantic_service()
	post_snapshot = cast(Any, db.collection("posts").document(post_id).get())
	if not post_snapshot.exists:
		raise ValueError(f"Post '{post_id}' was not found.")

	candidate = _prepare_post_for_indexing(post_snapshot=post_snapshot, db=db)
	if candidate is None:
		return {
			"postId": post_id,
			"indexed": False,
			"indexing_version": INDEXING_VERSION,
		}

	post_reference, resolved_post_id, document_text, metadata = candidate
	_set_post_index_status(post_reference, indexed=False)
	vector = get_openai_service().get_embedding(document_text)
	semantic_service.upsert(vector=vector, metadata=metadata, item_id=resolved_post_id)
	_set_post_index_status(post_reference, indexed=True)

	return {
		"postId": resolved_post_id,
		"indexed": True,
		"indexing_version": INDEXING_VERSION,
	}


def fetch_relevant_posts(query_text: str, limit: int = 20) -> list[dict[str, Any]]:
	load_dotenv()
	return get_semantic_service().query_posts(query_text=query_text, top_k=limit)


def _prepare_post_for_indexing(post_snapshot: Any, db: Any) -> tuple[Any, str, str, dict[str, Any]] | None:
	post_data = post_snapshot.to_dict() or {}
	post_reference = post_snapshot.reference
	target_id = str(post_data.get("targetId") or post_data.get("targetid") or "").strip()
	if not target_id:
		_set_post_index_status(post_reference, indexed=False)
		return None

	target_type = str(post_data.get("targetType") or post_data.get("targettype") or "").strip().lower()
	target_data = _load_target_data(db=db, target_type=target_type, target_id=target_id)
	document_text = _build_document_text(post_data, target_data)
	if not document_text.strip():
		_set_post_index_status(post_reference, indexed=False)
		return None

	metadata = {
		"postId": post_snapshot.id,
		"targetId": target_id,
		"targetType": target_type,
		"post": post_data,
		"documentText": document_text,
		"indexedAt": datetime.now(timezone.utc).isoformat(),
	}
	if target_data is not None:
		metadata["target"] = target_data
		if target_type in {"course", "courses"}:
			metadata["courseId"] = target_id
			metadata["course"] = target_data
	return post_reference, post_snapshot.id, metadata["documentText"], metadata


def _set_post_index_status(post_reference: Any, indexed: bool) -> None:
	post_reference.set({"indexed": indexed, "indexing_version": INDEXING_VERSION}, merge=True)


def _load_target_data(db: Any, target_type: str, target_id: str) -> dict[str, Any] | None:
	collection_name = TARGET_COLLECTIONS.get(target_type)
	if not collection_name:
		return None

	target_snapshot = cast(Any, db.collection(collection_name).document(target_id).get())
	if not target_snapshot.exists:
		return None

	data = target_snapshot.to_dict() or {}
	return {"id": target_snapshot.id, **data}


def _build_document_text(post_data: dict[str, Any], target_data: dict[str, Any] | None) -> str:
	parts = [
		_stringify_mapping("Post", post_data),
		_stringify_mapping("Target", target_data or {}),
	]
	return "\n\n".join(part for part in parts if part)


def _stringify_mapping(label: str, data: dict[str, Any]) -> str:
	values: list[str] = []
	for key, value in data.items():
		text = _stringify_value(value)
		if text:
			values.append(f"{key}: {text}")

	if not values:
		return ""

	return f"{label}\n" + "\n".join(values)


def _stringify_value(value: Any) -> str:
	if value is None:
		return ""

	if isinstance(value, dict):
		parts = [f"{key}={_stringify_value(inner_value)}" for key, inner_value in value.items()]
		return ", ".join(part for part in parts if part)

	if isinstance(value, list):
		parts = [_stringify_value(item) for item in value]
		return ", ".join(part for part in parts if part)

	return str(value)


if __name__ == "__main__":
	result = update_posts_index()
	print(result)
