from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

from app.services.moderation_service import ModerationService


load_dotenv()


def _gemini_key() -> str | None:
    return os.getenv("GCP_GEMINI_API_KEY")


@pytest.mark.integration
def test_gemini_moderation_live_response_shape():
    if not _gemini_key():
        pytest.skip("Gemini integration test skipped: no Gemini API key configured.")

    service = ModerationService()
    decision = service.moderate_post(
        {
            "text": "I liked this course and found the lectures helpful.",
            "targetId": "course-1",
            "targetType": "course",
            "rating": 5,
        }
    )

    assert decision.status in {"approved", "rejected", "review"}
    assert isinstance(decision.allowed, bool)
    assert isinstance(decision.violations, list)
    assert all(isinstance(item, str) for item in decision.violations)
    assert isinstance(decision.explanation, str)
    assert decision.explanation.strip() != ""
    assert isinstance(decision.model, str)
    assert decision.model.strip() != ""