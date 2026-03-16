from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import feed


class FakeTaskResult:
    def __init__(self, task_id: str):
        self.id = task_id


class FakeDoc:
    def __init__(self, doc_id: str, data: dict):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return dict(self._data)


class FakeDocRef:
    def __init__(self, doc_id: str):
        self.id = doc_id
        self.saved = None

    def set(self, payload):
        self.saved = dict(payload)


class FakeCollection:
    def __init__(self, docs=None, doc_ref: FakeDocRef | None = None):
        self._docs = docs or []
        self._doc_ref = doc_ref or FakeDocRef("new-doc")

    def stream(self):
        return list(self._docs)

    def limit(self, _n: int):
        return self

    def document(self):
        return self._doc_ref


class FakeDB:
    def __init__(self):
        self.post_ref = FakeDocRef("post-1")
        self.collections = {
            "profiles": FakeCollection(docs=[FakeDoc("p1", {"name": "A"})]),
            "cafeterias": FakeCollection(docs=[FakeDoc("c1", {"name": "Cafe"})]),
            "posts": FakeCollection(docs=[FakeDoc("po1", {"text": "hello"})], doc_ref=self.post_ref),
        }

    def collection(self, name: str):
        return self.collections[name]


def _client(monkeypatch, db: FakeDB) -> TestClient:
    app = FastAPI()
    monkeypatch.setattr(feed, "get_db_client", lambda: db)
    monkeypatch.setattr(feed.process_post_task, "delay", lambda post_id: FakeTaskResult("task-1"))
    app.include_router(feed.router)
    return TestClient(app)


def test_feed_endpoint_returns_mixed_items(monkeypatch):
    client = _client(monkeypatch, FakeDB())
    response = client.get("/feed?limit=3&user_id=u1")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) <= 3


def test_create_post_endpoint_queues_task(monkeypatch):
    db = FakeDB()
    client = _client(monkeypatch, db)
    response = client.post(
        "/posts",
        json={"rating": 5, "text": "great", "targetId": "course-1", "targetType": "course"},
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["taskId"] == "task-1"
    assert db.post_ref.saved is not None


def test_create_profile_validation(monkeypatch):
    client = _client(monkeypatch, FakeDB())
    response = client.post("/profiles", json={"name": "OnlyName"})
    assert response.status_code == 400
