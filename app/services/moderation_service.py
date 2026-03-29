from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from google import genai
from google.genai import types

_log = logging.getLogger(__name__)

ModerationStatus = Literal["approved", "rejected", "review"]
DEFAULT_GEMINI_MODEL = "gemini-1.5-flash"


@dataclass(slots=True)
class ModerationDecision:
    status: ModerationStatus
    allowed: bool
    violations: list[str]
    explanation: str
    model: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_SYSTEM_PROMPT = """\
You are a content moderation engine for AUB Social — a university platform where students
post reviews about courses, professors, campus life, and cafeterias.

Your sole task: evaluate a post payload against the provided moderation guidelines and
return a single JSON object. No markdown fences, no prose, no extra keys.

## Output schema
{
  "status":      "approved" | "rejected" | "review",
  "allowed":     true | false,
  "violations":  ["<short category label>", ...],
  "explanation": "<one factual sentence, max 25 words>"
}

## Decision rules
- approved  → content clearly complies with all guidelines; set allowed = true.
- rejected  → content clearly violates one or more guidelines; set allowed = false.
- review    → ambiguous, sarcastic, or context-dependent content; set allowed = false;
              a human moderator will decide.
- violations → empty array when status is "approved"; name the violated guideline
               category (e.g. "harassment", "hate speech", "doxxing") otherwise.
- explanation → state the specific concern plainly; do not moralize.

## Absolute prohibitions — always reject
  • Threats of violence or encouragement of self-harm
  • Hate speech or content degrading protected characteristics
  • Doxxing or disclosure of private personal information
  • Explicit sexual content or sexual coercion
  • Instructions for dangerous or illegal acts

## Non-violations — never penalize
  • Negative opinions or low ratings about courses, professors, or campus facilities
  • Mild profanity when not directed at a specific person as abuse
  • Criticism of institutional decisions or policies

## Evaluation principles
  1. Judge the post holistically; do not fixate on individual words out of context.
  2. Prefer "review" over "rejected" whenever intent or context is genuinely ambiguous.
  3. Protect users from targeted personal harm above all other considerations.
"""

_singleton: "ModerationService | None" = None


def get_moderation_service() -> "ModerationService":
    global _singleton
    if _singleton is None:
        _singleton = ModerationService()
    return _singleton


class ModerationService:
    def __init__(self) -> None:
        self._guidelines = _load_guidelines()
        self._model_name = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
        self._client: genai.Client | None = None
        self._enabled = False

        api_key = os.getenv("GCP_GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            _log.warning("GCP_GEMINI_API_KEY not set. Moderation will be disabled.")
            return

        try:
            self._client = genai.Client(api_key=api_key)
            self._enabled = True
            _log.info("ModerationService initialised with model %s.", self._model_name)
        except Exception as exc:
            _log.error("Failed to initialise Gemini client: %s. Moderation disabled.", exc)

    def moderate_post(self, post_data: dict[str, Any]) -> ModerationDecision:
        if not self._enabled or self._client is None:
            return ModerationDecision(
                status="review",
                allowed=False,
                violations=[],
                explanation="Moderation service unavailable; post queued for manual review.",
                model=self._model_name,
            )

        payload = json.dumps(post_data, ensure_ascii=True, sort_keys=True)
        prompt = (
            "## Moderation Guidelines\n"
            f"{self._guidelines}\n\n"
            "## Post Payload\n"
            f"{payload}"
        )
        response = _call_gemini(
            prompt=prompt,
            system_prompt=_SYSTEM_PROMPT,
            client=self._client,
            model=self._model_name,
        )
        return _parse_decision(response=response, model=self._model_name)


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


def _call_gemini(prompt: str, system_prompt: str, client: genai.Client, model: str) -> str:
    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
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