from __future__ import annotations

import pytest

from app.services import moderation_service as moderation


def test_parse_decision_handles_markdown_json():
    response = """```json
    {"status":"approved","allowed":true,"violations":[],"explanation":"ok"}
    ```"""

    result = moderation._parse_decision(response=response, model="gemini-x")

    assert result.status == "approved"
    assert result.allowed is True
    assert result.model == "gemini-x"


def test_parse_decision_defaults_to_review():
    response = '{"status":"unknown","allowed":true,"violations":["x"],"explanation":"hmm"}'
    result = moderation._parse_decision(response=response, model="m")
    assert result.status == "review"
    assert result.allowed is False


def test_constructor_requires_gcp_key(monkeypatch):
    monkeypatch.delenv("GCP_GEMINI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GCP_GEMINI_API_KEY"):
        moderation.ModerationService()


def test_call_gemini_uses_text_field():
    class FakeModels:
        @staticmethod
        def generate_content(model, contents, config):
            return type("Resp", (), {"text": "{\"status\":\"approved\",\"allowed\":true,\"violations\":[],\"explanation\":\"ok\"}"})()

    class FakeClient:
        models = FakeModels()

    out = moderation._call_gemini("p", FakeClient(), "m")
    assert "approved" in out
