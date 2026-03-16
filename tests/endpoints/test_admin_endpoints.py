from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.admin.dtos import AdminPostDTO, AdminProfileDTO, AdminUserDTO
from app.routers import admin


class FakeAdminService:
    def list_admin_profiles(self):
        return [
            AdminProfileDTO(
                id="p1",
                name="Jane Doe",
                location="beirut",
                ratingAvg=4.5,
                ratingCount=11,
                reports=1,
                status="active",
                createdAt="2026-03-10T10:00:00+00:00",
            )
        ]

    def list_admin_posts(self):
        return [
            AdminPostDTO(
                id="post-1",
                targetId="course-1",
                targetType="course",
                text="Great class",
                rating=5,
                reports=0,
                moderationStatus="pending",
                moderationAllowed=False,
                moderationExplanation=None,
                moderationViolations=[],
                forcedByAdmin=False,
                indexed=False,
                indexingVersion=None,
                createdAt="2026-03-10T10:00:00+00:00",
            )
        ]

    def admin_analytics(self):
        return {
            "generatedAt": "2026-03-10T10:00:00+00:00",
            "totals": {"usersTotal": 1, "profilesTotal": 1, "postsTotal": 1},
            "series7d": [{"day": "2026-03-10", "users": 1, "posts": 1}],
        }

    def list_admin_users(self):
        return [
            AdminUserDTO(
                id="u1",
                email="u1@mail.aub.edu",
                isVerified=True,
                status="active",
                createdAt="2026-03-10T10:00:00+00:00",
            )
        ]

    def delete_post(self, post_id: str):
        self.deleted_post = post_id

    def set_post_moderation(self, post_id: str, accepted: bool):
        return AdminPostDTO(
            id=post_id,
            targetId="course-1",
            targetType="course",
            text="ok",
            rating=4,
            reports=0,
            moderationStatus="approved" if accepted else "rejected",
            moderationAllowed=accepted,
            moderationExplanation="updated",
            moderationViolations=[],
            forcedByAdmin=True,
            indexed=accepted,
            indexingVersion=None,
            createdAt="2026-03-10T10:00:00+00:00",
        )

    def delete_user(self, user_id: str):
        self.deleted_user = user_id

    def set_user_banned(self, user_id: str, banned: bool):
        self.user_banned = (user_id, banned)

    def set_profile_banned(self, profile_id: str, banned: bool):
        self.profile_banned = (profile_id, banned)


def _client(monkeypatch) -> TestClient:
    app = FastAPI()
    monkeypatch.setattr(admin, "get_firebase_service", lambda: FakeAdminService())
    app.include_router(admin.router, prefix="/admin")
    return TestClient(app)


def test_admin_profiles_endpoint(monkeypatch):
    client = _client(monkeypatch)
    response = client.get("/admin/profiles")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == "p1"


def test_admin_set_post_moderation_endpoint(monkeypatch):
    client = _client(monkeypatch)
    response = client.patch("/admin/posts/post-1/moderation", json={"accepted": True})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["moderationStatus"] == "approved"
    assert payload["indexed"] is True


def test_admin_delete_user_invalid_id(monkeypatch):
    client = _client(monkeypatch)
    response = client.delete("/admin/users/__bad")
    assert response.status_code == 400


def test_admin_jobs_endpoint(monkeypatch):
    client = _client(monkeypatch)
    response = client.get("/admin/jobs")
    assert response.status_code == 200
    payload = response.json()
    assert "items" in payload
