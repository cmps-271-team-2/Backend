from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import jobs


class FakeTaskResult:
    def __init__(self, task_id: str):
        self.id = task_id


class FakeAsyncResult:
    def __init__(self, state: str = "SUCCESS", result=None):
        self.state = state
        self.result = result

    def ready(self):
        return self.state in {"SUCCESS", "FAILURE"}


def _client(monkeypatch) -> TestClient:
    app = FastAPI()
    monkeypatch.setattr(jobs.upload_post_task, "delay", lambda post_id: FakeTaskResult("up-1"))
    monkeypatch.setattr(jobs.update_posts_index_task, "delay", lambda: FakeTaskResult("idx-1"))
    monkeypatch.setattr(jobs.process_post_task, "delay", lambda post_id: FakeTaskResult("proc-1"))
    monkeypatch.setattr(jobs, "fetch_relevant_posts", lambda query_text, limit: [{"id": "p1", "score": 0.9}])
    app.include_router(jobs.router)
    return TestClient(app)


def test_upload_post_endpoint(monkeypatch):
    client = _client(monkeypatch)
    response = client.post("/upload_post", json={"post_id": "post-1"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"] == "up-1"


def test_fetched_relevant_posts_endpoint(monkeypatch):
    client = _client(monkeypatch)
    response = client.get("/fetched_relevant_posts", params={"query": "algo", "limit": 3})
    assert response.status_code == 200
    assert response.json()["posts"][0]["id"] == "p1"


def test_task_status_success(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(jobs, "AsyncResult", lambda task_id, app: FakeAsyncResult(state="SUCCESS", result={"ok": True}))
    response = client.get("/tasks/task-1")
    assert response.status_code == 200
    assert response.json()["status"] == "SUCCESS"


def test_task_status_failure(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(jobs, "AsyncResult", lambda task_id, app: FakeAsyncResult(state="FAILURE", result="boom"))
    response = client.get("/tasks/task-1")
    assert response.status_code == 500
