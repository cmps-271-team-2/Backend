from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from google import genai
from google.genai import types

ModerationStatus = Literal["approved", "rejected", "review"]
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


@dataclass(slots=True)
class ModerationDecision:
    status: ModerationStatus
    allowed: bool
    violations: list[str]
    explanation: str
    model: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_singleton: "ModerationService | None" = None


def get_moderation_service() -> "ModerationService":
    global _singleton
    if _singleton is None:
        _singleton = ModerationService()
    return _singleton


class ModerationService:
    def __init__(self) -> None:
        self._guidelines = _load_guidelines()
        self._api_key = os.getenv("GCP_GEMINI_API_KEY")
        if not self._api_key:
            raise ValueError("GCP_GEMINI_API_KEY not set in environment.")
        self._model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
        self._client = genai.Client(api_key=self._api_key)

    def moderate_post(self, post_data: dict[str, Any]) -> ModerationDecision:
        payload = json.dumps(post_data, ensure_ascii=True, sort_keys=True)
        prompt = (
            "You are a content moderation assistant for a university social app. "
            "Evaluate posts against the provided guidelines and respond with valid JSON only. "
            "Return an object with keys: status, allowed, violations, explanation. "
            "Status must be one of approved, rejected, review. "
            "Violations must be an array of short category strings. "
            "Explanation must be one short sentence.\n\n"
            "Guidelines:\n"
            f"{self._guidelines}\n\n"
            "Post payload:\n"
            f"{payload}\n\n"
            "Return JSON only."
        )
        response = _call_gemini(prompt=prompt, client=self._client, model=self._model)
        return _parse_decision(response=response, model=self._model)


def _load_guidelines() -> str:
    guidelines_path = Path(__file__).resolve().parent.parent / "data" / "post_moderation_guidelines.md"
    return guidelines_path.read_text(encoding="utf-8")


def _parse_decision(response: str, model: str) -> ModerationDecision:
    cleaned = response.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if len(lines) >= 3:
            cleaned = "\n".join(lines[1:-1]).strip()

    parsed = json.loads(cleaned)

    raw_status = str(parsed.get("status") or "review").strip().lower()
    status: ModerationStatus
    if raw_status == "approved":
        status = "approved"
    elif raw_status == "rejected":
        status = "rejected"
    else:
        status = "review"

    allowed = bool(parsed.get("allowed")) and status == "approved"
    violations_raw = parsed.get("violations") or []
    violations = [str(item) for item in violations_raw if str(item).strip()]
    explanation = str(parsed.get("explanation") or "No explanation provided.").strip()

    return ModerationDecision(
        status=status,
        allowed=allowed,
        violations=violations,
        explanation=explanation,
        model=model,
    )


def _call_gemini(prompt: str, client: genai.Client, model: str) -> str:
    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )
    except Exception as exc:
        raise RuntimeError(f"Gemini API request failed: {exc}") from exc

    text = str(getattr(response, "text", "") or "").strip()
    if text:
        return text

    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        raise RuntimeError("Gemini API response did not include candidates.")

    content = getattr(candidates[0], "content", None)
    parts = getattr(content, "parts", None) or []
    if not parts:
        raise RuntimeError("Gemini API response did not include content parts.")

    fallback_text = str(getattr(parts[0], "text", "") or "").strip()
    if not fallback_text:
        raise RuntimeError("Gemini API response returned empty moderation content.")
    return fallback_text