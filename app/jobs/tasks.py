from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.firebase_admin import init_firebase_admin
from app.core.firestore import get_db
from app.jobs.celery_app import celery_app
from app.jobs.index_posts import update_posts_index, upload_post
from app.services.moderation_service import get_moderation_service
from app.services.semantic_service import get_semantic_service


@celery_app.task(name="jobs.update_posts_index")
def update_posts_index_task() -> dict[str, int]:
    return update_posts_index()


@celery_app.task(name="jobs.upload_post")
def upload_post_task(post_id: str) -> dict[str, Any]:
    return upload_post(post_id)


@celery_app.task(name="jobs.process_post")
def process_post_task(post_id: str) -> dict[str, Any]:
    init_firebase_admin()
    db = get_db()
    post_ref = db.collection("posts").document(post_id)
    snapshot = post_ref.get()

    if not snapshot.exists:
        raise ValueError(f"Post '{post_id}' was not found.")

    post_data = snapshot.to_dict() or {}
    decision = get_moderation_service().moderate_post(post_data)
    checked_at = datetime.now(timezone.utc).isoformat()
    moderation_payload = {
        "status": decision.status,
        "allowed": decision.allowed,
        "violations": decision.violations,
        "explanation": decision.explanation,
        "model": decision.model,
        "checkedAt": checked_at,
    }

    if not decision.allowed:
        get_semantic_service().delete(post_id)
        post_ref.set({"moderation": moderation_payload, "indexed": False}, merge=True)
        return {
            "postId": post_id,
            "indexed": False,
            "moderation": moderation_payload,
        }

    index_result = upload_post(post_id)
    post_ref.set({"moderation": moderation_payload}, merge=True)

    return {
        "postId": post_id,
        "indexed": bool(index_result.get("indexed")),
        "indexing": index_result,
        "moderation": moderation_payload,
    }
