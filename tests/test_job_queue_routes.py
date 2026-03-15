from __future__ import annotations

import asyncio
import json
from typing import Any, cast

from app.feed import routes as feed_routes
from app.jobs import routes as job_routes


class DummyTaskResult:
    def __init__(self, task_id: str) -> None:
        self.id = task_id


def test_upload_post_endpoint_enqueues_task(monkeypatch):
    monkeypatch.setattr(
        job_routes.upload_post_task,
        "delay",
        lambda post_id: DummyTaskResult("upload-task-1"),
    )

    payload = job_routes.UploadPostRequest(post_id="post-123")
    result = job_routes.upload_post_endpoint(payload)

    assert result["status"] == "queued"
    assert result["task_id"] == "upload-task-1"
    assert result["post_id"] == "post-123"


def test_update_posts_index_endpoint_enqueues_task(monkeypatch):
    monkeypatch.setattr(
        job_routes.update_posts_index_task,
        "delay",
        lambda: DummyTaskResult("index-task-1"),
    )

    result = job_routes.update_posts_index_endpoint()

    assert result["status"] == "queued"
    assert result["task_id"] == "index-task-1"


class FakeRequest:
    def __init__(self, payload: dict):
        self._payload = payload

    async def json(self):
        return self._payload


class FakeDocRef:
    def __init__(self, doc_id: str) -> None:
        self.id = doc_id
        self.saved = None

    def set(self, data, merge=False):
        self.saved = {"data": data, "merge": merge}


class FakeCollection:
    def __init__(self, doc_ref: FakeDocRef):
        self._doc_ref = doc_ref

    def document(self):
        return self._doc_ref


class FakeDB:
    def __init__(self, doc_ref: FakeDocRef):
        self._doc_ref = doc_ref

    def collection(self, name: str):
        assert name == "posts"
        return FakeCollection(self._doc_ref)


def test_create_post_queues_processing_task(monkeypatch):
    doc_ref = FakeDocRef("post-999")
    monkeypatch.setattr(feed_routes, "get_db_client", lambda: FakeDB(doc_ref))
    monkeypatch.setattr(
        feed_routes.process_post_task,
        "delay",
        lambda post_id: DummyTaskResult("process-task-1"),
    )

    request = FakeRequest(
        {
            "rating": 5,
            "text": "Great class",
            "targetId": "course-1",
            "targetType": "course",
        }
    )

    response = asyncio.run(feed_routes.create_post(cast(Any, request)))
    payload = json.loads(bytes(response.body).decode("utf-8"))

    assert response.status_code == 202
    assert payload["id"] == "post-999"
    assert payload["status"] == "queued"
    assert payload["taskId"] == "process-task-1"
    assert doc_ref.saved is not None
