from __future__ import annotations

from app.jobs import tasks
from app.services.moderation_service import ModerationDecision


class FakeSnapshot:
    def __init__(self, exists: bool, data: dict | None = None):
        self.exists = exists
        self._data = data or {}

    def to_dict(self):
        return dict(self._data)


class FakeDocRef:
    def __init__(self, snapshot: FakeSnapshot):
        self._snapshot = snapshot
        self.writes = []

    def get(self):
        return self._snapshot

    def set(self, payload, merge=False):
        self.writes.append({"payload": payload, "merge": merge})


class FakeCollection:
    def __init__(self, doc_ref: FakeDocRef):
        self._doc_ref = doc_ref

    def document(self, doc_id: str):
        assert doc_id == "post-1"
        return self._doc_ref


class FakeDB:
    def __init__(self, doc_ref: FakeDocRef):
        self._doc_ref = doc_ref

    def collection(self, name: str):
        assert name == "posts"
        return FakeCollection(self._doc_ref)


class FakeModerationService:
    def __init__(self, decision: ModerationDecision):
        self._decision = decision

    def moderate_post(self, post_data):
        return self._decision


class FakeSemanticService:
    def __init__(self):
        self.deleted_ids = []

    def delete(self, post_id: str):
        self.deleted_ids.append(post_id)


def test_process_post_task_approved(monkeypatch):
    snapshot = FakeSnapshot(True, {"text": "hello", "targetId": "abc", "targetType": "course"})
    doc_ref = FakeDocRef(snapshot)

    monkeypatch.setattr(tasks, "init_firebase_admin", lambda: None)
    monkeypatch.setattr(tasks, "get_db", lambda: FakeDB(doc_ref))
    monkeypatch.setattr(
        tasks,
        "get_moderation_service",
        lambda: FakeModerationService(
            ModerationDecision(
                status="approved",
                allowed=True,
                violations=[],
                explanation="Looks good",
                model="gemini-1.5-flash",
            )
        ),
    )
    monkeypatch.setattr(tasks, "upload_post", lambda post_id: {"postId": post_id, "indexed": True})

    result = tasks.process_post_task("post-1")

    assert result["postId"] == "post-1"
    assert result["indexed"] is True
    assert len(doc_ref.writes) == 1
    assert doc_ref.writes[0]["payload"]["moderation"]["status"] == "approved"


def test_process_post_task_rejected(monkeypatch):
    snapshot = FakeSnapshot(True, {"text": "bad", "targetId": "abc", "targetType": "course"})
    doc_ref = FakeDocRef(snapshot)
    semantic = FakeSemanticService()

    monkeypatch.setattr(tasks, "init_firebase_admin", lambda: None)
    monkeypatch.setattr(tasks, "get_db", lambda: FakeDB(doc_ref))
    monkeypatch.setattr(
        tasks,
        "get_moderation_service",
        lambda: FakeModerationService(
            ModerationDecision(
                status="rejected",
                allowed=False,
                violations=["abuse"],
                explanation="Rule violation",
                model="gemini-1.5-flash",
            )
        ),
    )
    monkeypatch.setattr(tasks, "get_semantic_service", lambda: semantic)

    result = tasks.process_post_task("post-1")

    assert result["postId"] == "post-1"
    assert result["indexed"] is False
    assert semantic.deleted_ids == ["post-1"]
    assert len(doc_ref.writes) == 1
    assert doc_ref.writes[0]["payload"]["moderation"]["status"] == "rejected"
    assert doc_ref.writes[0]["payload"]["indexed"] is False
