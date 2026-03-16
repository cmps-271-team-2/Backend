from __future__ import annotations

from datetime import datetime, timezone

from app.services import firebase_service


class FakeDocSnapshot:
    def __init__(self, doc_id: str, data: dict | None):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data or {})


class FakeDocRef:
    def __init__(self, doc_id: str, store: dict[str, dict]):
        self.id = doc_id
        self._store = store

    def get(self):
        return FakeDocSnapshot(self.id, self._store.get(self.id))

    def set(self, payload, merge=False):
        if merge:
            merged = dict(self._store.get(self.id, {}))
            merged.update(payload)
            self._store[self.id] = merged
        else:
            self._store[self.id] = dict(payload)

    def delete(self):
        self._store.pop(self.id, None)


class FakeCollection:
    def __init__(self, store: dict[str, dict]):
        self._store = store

    def limit(self, _n):
        return self

    def stream(self):
        return [FakeDocSnapshot(doc_id, data) for doc_id, data in self._store.items()]

    def document(self, doc_id: str):
        return FakeDocRef(doc_id, self._store)


class FakeDB:
    def __init__(self):
        self.data = {
            "profiles": {
                "p1": {
                    "name": "Prof A",
                    "location": "beirut",
                    "RatingAvg": 4.2,
                    "RatingCount": 10,
                    "reports": 1,
                    "CreatedAt": datetime.now(timezone.utc).isoformat(),
                }
            },
            "posts": {
                "post-1": {
                    "text": "Great",
                    "targetId": "course-1",
                    "targetType": "course",
                    "rating": 5,
                    "moderation": {"status": "pending", "allowed": False},
                    "createdAt": datetime.now(timezone.utc).isoformat(),
                }
            },
            "users": {
                "u1": {
                    "email": "u1@mail.aub.edu",
                    "isVerified": True,
                    "createdAt": datetime.now(timezone.utc).isoformat(),
                }
            },
        }

    def collection(self, name: str):
        return FakeCollection(self.data[name])


class FakeSemantic:
    def __init__(self):
        self.deleted = []

    def delete(self, post_id: str):
        self.deleted.append(post_id)


def _service(monkeypatch, db: FakeDB, semantic_obj: FakeSemantic):
    monkeypatch.setattr(firebase_service, "load_dotenv", lambda: None)
    monkeypatch.setattr(firebase_service, "init_firebase_admin", lambda: None)
    monkeypatch.setattr(firebase_service, "get_db", lambda: db)
    monkeypatch.setattr(firebase_service, "get_semantic_service", lambda: semantic_obj)
    return firebase_service.FirebaseService()


def test_list_admin_profiles(monkeypatch):
    service = _service(monkeypatch, FakeDB(), FakeSemantic())
    profiles = service.list_admin_profiles()
    assert len(profiles) == 1
    assert profiles[0].id == "p1"
    assert profiles[0].ratingAvg == 4.2


def test_set_post_moderation_approved_indexes(monkeypatch):
    db = FakeDB()
    semantic_obj = FakeSemantic()
    service = _service(monkeypatch, db, semantic_obj)

    monkeypatch.setattr(firebase_service, "upload_post", lambda post_id: {"indexed": True, "postId": post_id})

    post = service.set_post_moderation("post-1", accepted=True)

    assert post.moderationStatus == "approved"
    assert post.indexed is True


def test_set_post_moderation_rejected_deletes_index(monkeypatch):
    db = FakeDB()
    semantic_obj = FakeSemantic()
    service = _service(monkeypatch, db, semantic_obj)

    post = service.set_post_moderation("post-1", accepted=False)

    assert post.moderationStatus == "rejected"
    assert post.indexed is False
    assert semantic_obj.deleted == ["post-1"]
