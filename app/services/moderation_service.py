from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from app.services.openai_service import LLM_MODEL, get_openai_service


ModerationStatus = Literal["approved", "rejected", "review"]


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
        self._openai_service = get_openai_service()

    def moderate_post(self, post_data: dict[str, Any]) -> ModerationDecision:
        payload = json.dumps(post_data, ensure_ascii=True, sort_keys=True)
        response = self._openai_service.generate_llm_response(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a content moderation assistant for a university social app. "
                        "Evaluate posts against the provided guidelines and respond with valid JSON only. "
                        'Return an object with keys: status, allowed, violations, explanation. '
                        'Status must be one of approved, rejected, review. '
                        "Violations must be an array of short category strings. "
                        "Explanation must be one short sentence."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Guidelines:\n"
                        f"{self._guidelines}\n\n"
                        "Post payload:\n"
                        f"{payload}\n\n"
                        "Return JSON only."
                    ),
                },
            ]
        )
        return _parse_decision(response)


def _load_guidelines() -> str:
    guidelines_path = Path(__file__).resolve().parent.parent / "data" / "post_moderation_guidelines.md"
    return guidelines_path.read_text(encoding="utf-8")


def _parse_decision(response: str) -> ModerationDecision:
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
        model=LLM_MODEL,
    )