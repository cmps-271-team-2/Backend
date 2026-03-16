# tests/test_feed.py
import sys
import types
import importlib


def import_app_with_firebase_stub():
    """
    Stubs firebase_admin + firestore so importing app.py doesn't require real Firebase.
    """
    # --- firebase_admin stub ---
    firebase_admin_stub = types.SimpleNamespace(
        initialize_app=lambda cred=None: None
    )

    # --- credentials stub ---
    credentials_stub = types.SimpleNamespace(
        Certificate=lambda path: object()
    )

    # --- firestore stub (only needs .client()) ---
    firestore_stub = types.SimpleNamespace(
        client=lambda: object()
    )

    # Create module firebase_admin and firebase_admin.credentials/firestore
    firebase_admin_module = types.ModuleType("firebase_admin")
    firebase_admin_module.initialize_app = firebase_admin_stub.initialize_app

    firebase_admin_credentials_module = types.ModuleType("firebase_admin.credentials")
    firebase_admin_credentials_module.Certificate = credentials_stub.Certificate

    firebase_admin_firestore_module = types.ModuleType("firebase_admin.firestore")
    firebase_admin_firestore_module.client = firestore_stub.client

    # Inject into sys.modules BEFORE importing app
    sys.modules["firebase_admin"] = firebase_admin_module
    sys.modules["firebase_admin.credentials"] = firebase_admin_credentials_module
    sys.modules["firebase_admin.firestore"] = firebase_admin_firestore_module

    # Now import/reload app safely
    import app
    importlib.reload(app)
    return app


def test_build_mixed_feed_is_deterministic_with_seed():
    app = import_app_with_firebase_stub()
    build_mixed_feed = app.build_mixed_feed

    items = (
        [{"id": f"p{i}", "type": "profile"} for i in range(6)] +
        [{"id": f"c{i}", "type": "cafeteria"} for i in range(6)] +
        [{"id": f"post{i}", "type": "post"} for i in range(6)]
    )

    weights = {"profile": 2, "cafeteria": 1, "post": 1}

    feed1 = build_mixed_feed(items, page_size=10, weights=weights, max_streak=2, seed=123)
    feed2 = build_mixed_feed(items, page_size=10, weights=weights, max_streak=2, seed=123)

    assert feed1 == feed2
    assert len(feed1) == 10
    assert all("type" in x for x in feed1)


def test_build_mixed_feed_respects_max_streak_when_alternatives_exist():
    app = import_app_with_firebase_stub()
    build_mixed_feed = app.build_mixed_feed

    # Plenty of alternatives so it shouldn't need to "relax" streak rule
    items = (
        [{"id": f"p{i}", "type": "profile"} for i in range(10)] +
        [{"id": f"c{i}", "type": "cafeteria"} for i in range(10)] +
        [{"id": f"post{i}", "type": "post"} for i in range(10)]
    )

    weights = {"profile": 3, "cafeteria": 2, "post": 2}
    max_streak = 2

    feed = build_mixed_feed(items, page_size=25, weights=weights, max_streak=max_streak, seed=999)

    # Check no more than 2 consecutive same "type"
    streak = 1
    for i in range(1, len(feed)):
        if feed[i]["type"] == feed[i - 1]["type"]:
            streak += 1
            assert streak <= max_streak
        else:
            streak = 1