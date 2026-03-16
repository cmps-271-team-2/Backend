from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import reviews


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(reviews.router)
    return TestClient(app)


def test_get_reviews_endpoint():
    client = _client()
    response = client.get("/reviews", params={"user_id": "u1"})
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert "has_liked" in payload[0]


def test_review_action_like_toggle():
    client = _client()
    first = client.post("/reviews/action", json={"review_id": 1, "user_id": "u1", "action": "like"})
    assert first.status_code == 200
    second = client.post("/reviews/action", json={"review_id": 1, "user_id": "u1", "action": "like"})
    assert second.status_code == 200


def test_review_action_not_found():
    client = _client()
    response = client.post("/reviews/action", json={"review_id": 999, "user_id": "u1", "action": "like"})
    assert response.status_code == 404
