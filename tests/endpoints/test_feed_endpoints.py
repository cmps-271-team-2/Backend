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


class FakeSnapshot:
    def __init__(self, doc_id: str, data: dict | None):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else {}


class FakeDocRef:
    def __init__(self, doc_id: str, initial_data: dict | None = None):
        self.id = doc_id
        self.saved = None
        self._data = initial_data

    def set(self, payload, merge=False):
        if merge:
            if self._data is None:
                self._data = {}
            self._data.update(payload)
        else:
            self.saved = dict(payload)
            self._data = dict(payload)

    def get(self):
        return FakeSnapshot(self.id, self._data)


class FakeCollection:
    def __init__(self, docs=None, doc_ref: FakeDocRef | None = None):
        self._docs = docs or []
        self._doc_ref = doc_ref or FakeDocRef("new-doc")
        self._doc_refs: dict[str, FakeDocRef] = {}

    def stream(self):
        return list(self._docs)

    def limit(self, _n: int):
        return self

    def order_by(self, _field, direction=None):
        return self

    def document(self, doc_id: str | None = None):
        if doc_id is None:
            return self._doc_ref
        if doc_id not in self._doc_refs:
            self._doc_refs[doc_id] = FakeDocRef(doc_id)
        return self._doc_refs[doc_id]


class FakeDB:
    def __init__(self):
        self.post_ref = FakeDocRef("post-1")
        self.collections: dict[str, FakeCollection] = {
            "profiles": FakeCollection(docs=[FakeDoc("p1", {"name": "A"})]),
            "cafeterias": FakeCollection(docs=[FakeDoc("c1", {"name": "Cafe"})]),
            "posts": FakeCollection(docs=[FakeDoc("po1", {"text": "hello"})], doc_ref=self.post_ref),
            "users": FakeCollection(),
        }

    def collection(self, name: str):
        if name not in self.collections:
            self.collections[name] = FakeCollection()
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


def test_like_post_stores_recommendation_prompt(monkeypatch):
    db = FakeDB()
    post_ref = FakeDocRef("po1", initial_data={"text": "Great algorithms class", "targetType": "course", "targetId": "CS101", "likedBy": []})
    db.collections["posts"]._doc_refs["po1"] = post_ref
    user_ref = FakeDocRef("u1", initial_data={})
    db.collections["users"]._doc_refs["u1"] = user_ref

    client = _client(monkeypatch, db)
    response = client.post("/posts/po1/like", json={"user_id": "u1"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["liked"] is True
    assert payload["likes"] == 1
    prompt = (user_ref._data or {}).get("recommendationPrompt", "")
    assert "CS101" in prompt
    assert "Great algorithms class" in prompt


def test_like_post_unlike_does_not_update_prompt(monkeypatch):
    db = FakeDB()
    original_prompt = "cafeteria MainDining: Good food"
    post_ref = FakeDocRef("po1", initial_data={"text": "Good food", "targetType": "cafeteria", "targetId": "MainDining", "likedBy": ["u1"]})
    db.collections["posts"]._doc_refs["po1"] = post_ref
    user_ref = FakeDocRef("u1", initial_data={"recommendationPrompt": original_prompt})
    db.collections["users"]._doc_refs["u1"] = user_ref

    client = _client(monkeypatch, db)
    response = client.post("/posts/po1/like", json={"user_id": "u1"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["liked"] is False
    assert payload["likes"] == 0
    assert (user_ref._data or {}).get("recommendationPrompt") == original_prompt


def test_like_post_not_found(monkeypatch):
    db = FakeDB()
    client = _client(monkeypatch, db)
    response = client.post("/posts/nonexistent/like", json={"user_id": "u1"})
    assert response.status_code == 404


def test_feed_uses_recommendation_prompt(monkeypatch):
    db = FakeDB()
    user_ref = FakeDocRef("u1", initial_data={"recommendationPrompt": "course CS101: Great algorithms"})
    db.collections["users"]._doc_refs["u1"] = user_ref

    semantic_posts = [{"id": "sem-1", "text": "Algorithms post", "targetType": "course", "targetId": "CS101", "score": 0.95}]
    monkeypatch.setattr(feed, "fetch_relevant_posts", lambda prompt, limit: semantic_posts)

    client = _client(monkeypatch, db)
    response = client.get("/feed?limit=5&user_id=u1")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    post_items = [item for item in payload if item.get("type") == "post"]
    assert any(p.get("id") == "sem-1" for p in post_items)


def test_get_posts_excludes_non_indexed_posts(monkeypatch):
    """GET /posts should only return posts that are indexed and approved."""
    db = FakeDB()
    approved_post = FakeDoc("po-approved", {
        "text": "visible",
        "createdAt": "2025-01-01",
        "indexed": True,
        "moderation": {"status": "approved", "allowed": True},
    })
    pending_post = FakeDoc("po-pending", {
        "text": "hidden",
        "createdAt": "2025-01-02",
        "indexed": False,
        "moderation": {"status": "pending", "allowed": False},
    })
    rejected_post = FakeDoc("po-rejected", {
        "text": "rejected",
        "createdAt": "2025-01-03",
        "indexed": False,
        "moderation": {"status": "rejected", "allowed": False},
    })
    db.collections["posts"] = FakeCollection(
        docs=[approved_post, pending_post, rejected_post],
        doc_ref=db.post_ref,
    )

    client = _client(monkeypatch, db)
    response = client.get("/posts")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == "po-approved"


def test_feed_excludes_non_indexed_posts_in_fallback(monkeypatch):
    """GET /feed fallback path (no recommendation prompt) should only return indexed+approved posts."""
    db = FakeDB()
    approved_post = FakeDoc("po-ok", {
        "text": "visible",
        "indexed": True,
        "moderation": {"status": "approved", "allowed": True},
    })
    pending_post = FakeDoc("po-no", {
        "text": "hidden",
        "indexed": False,
        "moderation": {"status": "pending", "allowed": False},
    })
    db.collections["posts"] = FakeCollection(
        docs=[approved_post, pending_post],
        doc_ref=db.post_ref,
    )

    client = _client(monkeypatch, db)
    response = client.get("/feed?limit=20&user_id=guest&include_posts=true")
    assert response.status_code == 200
    payload = response.json()
    post_items = [item for item in payload if item.get("type") == "post"]
    assert len(post_items) == 1
    assert post_items[0]["id"] == "po-ok"


def test_feed_excludes_all_posts_when_none_indexed(monkeypatch):
    """GET /feed should return no posts when all are pending/rejected."""
    db = FakeDB()
    pending_post = FakeDoc("po-pending", {
        "text": "hidden",
        "indexed": False,
        "moderation": {"status": "pending", "allowed": False},
    })
    db.collections["posts"] = FakeCollection(
        docs=[pending_post],
        doc_ref=db.post_ref,
    )

    client = _client(monkeypatch, db)
    response = client.get("/feed?limit=20&user_id=guest&include_posts=true")
    assert response.status_code == 200
    payload = response.json()
    post_items = [item for item in payload if item.get("type") == "post"]
    assert len(post_items) == 0
