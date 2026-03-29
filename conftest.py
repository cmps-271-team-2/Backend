"""
Root conftest.py: mock out Firebase so unit tests can import app modules
without needing real Firebase credentials.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Stub firebase_admin before any app module imports it
# ---------------------------------------------------------------------------
firebase_admin_mock = MagicMock()
firebase_admin_mock._apps = {}

# firestore sub-module stubs
firestore_mock = MagicMock()
firebase_admin_mock.firestore = firestore_mock

# Make firebase_admin.initialize_app a no-op
firebase_admin_mock.initialize_app = MagicMock()

sys.modules.setdefault("firebase_admin", firebase_admin_mock)
sys.modules.setdefault("firebase_admin.firestore", firestore_mock)
sys.modules.setdefault("firebase_admin.credentials", MagicMock())
sys.modules.setdefault("firebase_admin.auth", MagicMock())
