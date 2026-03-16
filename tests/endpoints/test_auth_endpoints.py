from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import auth


class FakeDocumentSnapshot:
    def __init__(self, data=None):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data or {})


class FakeDocumentRef:
    def __init__(self, store: dict[str, dict], doc_id: str):
        self._store = store
        self._doc_id = doc_id

    def get(self):
        return FakeDocumentSnapshot(self._store.get(self._doc_id))

    def set(self, data, merge=False):
        if merge and self._doc_id in self._store:
            merged = dict(self._store[self._doc_id])
            merged.update(data)
            self._store[self._doc_id] = merged
            return
        self._store[self._doc_id] = dict(data)

    def update(self, data):
        existing = dict(self._store.get(self._doc_id, {}))
        existing.update(data)
        self._store[self._doc_id] = existing


class FakeCollection:
    def __init__(self, store: dict[str, dict]):
        self._store = store

    def document(self, doc_id: str):
        return FakeDocumentRef(self._store, doc_id)


class FakeDB:
    def __init__(self):
        self.collections: dict[str, dict[str, dict]] = {}

    def collection(self, name: str):
        if name not in self.collections:
            self.collections[name] = {}
        return FakeCollection(self.collections[name])


class FakeUser:
    def __init__(self, uid: str, email: str = "x@mail.aub.edu"):
        self.uid = uid
        self.email = email


class FakeFirebaseAuth:
    def __init__(self):
        self._users_by_email: dict[str, FakeUser] = {}

    def verify_id_token(self, token: str):
        if token == "ok-token":
            return {"uid": "u1", "email": "u1@mail.aub.edu"}
        raise ValueError("bad token")

    def get_user_by_email(self, email: str):
        if email in self._users_by_email:
            return self._users_by_email[email]
        raise ValueError("not found")

    def create_user(self, email: str, password: str, disabled: bool):
        user = FakeUser(uid="new-uid", email=email)
        self._users_by_email[email] = user
        return user

    def update_user(self, uid: str, **kwargs):
        return None

    def get_user(self, uid: str):
        return FakeUser(uid=uid, email="u1@mail.aub.edu")


def _client(monkeypatch, db: FakeDB, firebase_auth: FakeFirebaseAuth) -> TestClient:
    app = FastAPI()
    monkeypatch.setattr(auth, "get_db", lambda: db)
    monkeypatch.setattr(auth, "get_firebase_auth", lambda: firebase_auth)
    monkeypatch.setattr(auth, "send_otp_email", lambda email, otp: None)
    monkeypatch.setattr(auth, "send_password_reset_otp_email", lambda email, otp: None)
    monkeypatch.setattr(auth, "generate_otp", lambda: "123456")
    monkeypatch.setattr(auth, "verify_firebase_password", lambda email, pwd: True)
    app.include_router(auth.router, prefix="/auth")
    return TestClient(app)


def test_request_otp_rejects_non_aub_domain(monkeypatch):
    db = FakeDB()
    firebase_auth = FakeFirebaseAuth()
    client = _client(monkeypatch, db, firebase_auth)

    response = client.post(
        "/auth/register/request-otp",
        json={"email": "user@gmail.com", "password": "strongpass1"},
    )

    assert response.status_code == 400
    assert "@mail.aub.edu" in response.json()["detail"]


def test_request_otp_success(monkeypatch):
    db = FakeDB()
    firebase_auth = FakeFirebaseAuth()
    client = _client(monkeypatch, db, firebase_auth)

    response = client.post(
        "/auth/register/request-otp",
        json={"email": "user@mail.aub.edu", "password": "strongpass1"},
    )

    assert response.status_code == 200
    assert response.json()["message"] in {"OTP sent to your email.", "PENDING_VERIFICATION"}


def test_verify_otp_success_creates_user(monkeypatch):
    db = FakeDB()
    firebase_auth = FakeFirebaseAuth()
    client = _client(monkeypatch, db, firebase_auth)

    email = "user@mail.aub.edu"
    db.collection("pending_registrations").document(email).set(
        {
            "email": email,
            "password": "strongpass1",
            "otpHash": auth.hash_otp("123456"),
            "expiresAt": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "verifyAttempts": 0,
            "used": False,
        }
    )

    response = client.post(
        "/auth/register/verify-otp",
        json={"email": email, "otp": "123456"},
    )

    assert response.status_code == 200
    assert "activated" in response.json()["message"].lower()


def test_change_password_requires_auth_header(monkeypatch):
    db = FakeDB()
    firebase_auth = FakeFirebaseAuth()
    client = _client(monkeypatch, db, firebase_auth)

    response = client.post(
        "/auth/change-password",
        json={"current_password": "oldpass11", "new_password": "newpass11"},
    )

    assert response.status_code == 401
