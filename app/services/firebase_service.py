from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from dotenv import load_dotenv

from app.admin.dtos import AdminPostDTO, AdminProfileDTO, AdminStatusDTO, AdminUserDTO, AnalyticsDTO, SeriesPointDTO
from app.core.firebase_admin import get_firebase_auth, init_firebase_admin
from app.core.firestore import get_db
from app.jobs.index_posts import upload_post
from app.services.semantic_service import get_semantic_service


_singleton: "FirebaseService | None" = None


def get_firebase_service() -> "FirebaseService":
    global _singleton
    if _singleton is None:
        _singleton = FirebaseService()
    return _singleton


class FirebaseService:
    """Singleton service wrapper around Firebase Admin SDK clients.

    For now this only exposes the read operations the Admin dashboard needs.
    """

    def __init__(self) -> None:
        # Keep this safe to import in scripts/tests: ensure Firebase is initialized.
        load_dotenv()
        init_firebase_admin()
        self._db = get_db()

    @property
    def db(self):
        return self._db

    def list_admin_profiles(self) -> list[AdminProfileDTO]:
        # Firestore schema (from your screenshots): profiles/{id}: { name, location?, RatingAvg, RatingCount, CreatedAt }
        docs = self._db.collection("profiles").limit(5000).stream()
        out: list[AdminProfileDTO] = []
        for d in docs:
            data = d.to_dict() or {}
            name = str(data.get("name") or data.get("displayName") or d.id)
            location = data.get("location")
            created_at = _to_iso(data.get("CreatedAt") or data.get("createdAt"))

            rating_avg = _to_float(data.get("RatingAvg") or data.get("ratingAvg") or 0)
            rating_count = _to_int(data.get("RatingCount") or data.get("ratingCount") or 0)
            reports = _to_int(data.get("reports") or data.get("Reports") or data.get("reportCount") or 0)
            status = _to_status(data.get("status"), data.get("banned"))

            out.append(
                AdminProfileDTO(
                    id=d.id,
                    name=name,
                    location=str(location) if location is not None else None,
                    ratingAvg=rating_avg,
                    ratingCount=rating_count,
                    reports=reports,
                    status=status,
                    createdAt=created_at,
                )
            )

        # deterministic ordering for UX
        out.sort(key=lambda p: p.createdAt, reverse=True)
        return out

    def list_admin_posts(self) -> list[AdminPostDTO]:
        # Firestore schema (from your screenshots): posts/{id}: { Rating, createdAt, targetId, targetType, text }
        docs = self._db.collection("posts").limit(5000).stream()
        out: list[AdminPostDTO] = []
        for d in docs:
            data = d.to_dict() or {}

            text = str(data.get("text") or "")
            target_id = str(data.get("targetId") or "")
            target_type = str(data.get("targetType") or "")
            created_at = _to_iso(data.get("createdAt") or data.get("CreatedAt"))

            rating_raw = data.get("rating") if data.get("rating") is not None else data.get("Rating")
            rating = _to_int(rating_raw)
            reports = _to_int(data.get("reports") or data.get("Reports") or data.get("reportCount") or 0)
            moderation = data.get("moderation") if isinstance(data.get("moderation"), dict) else {}

            out.append(
                AdminPostDTO(
                    id=d.id,
                    targetId=target_id,
                    targetType=target_type,
                    text=text,
                    rating=rating,
                    reports=reports,
                    moderationStatus=_to_moderation_status(moderation.get("status")),
                    moderationAllowed=bool(moderation.get("allowed") is True),
                    moderationExplanation=_to_optional_str(moderation.get("explanation")),
                    moderationViolations=_to_str_list(moderation.get("violations")),
                    forcedByAdmin=bool(moderation.get("forcedByAdmin") is True),
                    indexed=bool(data.get("indexed") is True),
                    indexingVersion=_to_optional_int(data.get("indexing_version") or data.get("indexingVersion")),
                    createdAt=created_at,
                )
            )

        out.sort(key=lambda p: p.createdAt, reverse=True)
        return out

    def list_admin_users(self) -> list[AdminUserDTO]:
        docs = self._db.collection("users").limit(5000).stream()
        out: list[AdminUserDTO] = []
        for d in docs:
            data = d.to_dict() or {}
            email = str(data.get("email") or "")
            created_at = _to_iso(data.get("createdAt") or data.get("CreatedAt"))
            is_verified = bool(data.get("isVerified") is True)
            status = _to_status(data.get("status"), data.get("banned"))
            out.append(
                AdminUserDTO(
                    id=d.id,
                    email=email,
                    isVerified=is_verified,
                    status=status,
                    createdAt=created_at,
                )
            )

        out.sort(key=lambda u: u.createdAt, reverse=True)
        return out

    def delete_post(self, post_id: str) -> None:
        get_semantic_service().delete(post_id)
        self._db.collection("posts").document(post_id).delete()

    def set_post_moderation(self, post_id: str, accepted: bool) -> AdminPostDTO:
        post_ref = self._db.collection("posts").document(post_id)
        snapshot = post_ref.get()
        if not snapshot.exists:
            raise ValueError(f"Post '{post_id}' was not found.")

        checked_at = datetime.now(timezone.utc).isoformat()
        moderation_payload = {
            "status": "approved" if accepted else "rejected",
            "allowed": accepted,
            "violations": [] if accepted else ["admin-rejected"],
            "explanation": "Approved by admin." if accepted else "Rejected by admin.",
            "checkedAt": checked_at,
            "forcedByAdmin": True,
        }

        indexed = False
        if accepted:
            index_result = upload_post(post_id)
            indexed = bool(index_result.get("indexed"))
        else:
            get_semantic_service().delete(post_id)

        post_ref.set(
            {
                "moderation": moderation_payload,
                "indexed": indexed,
            },
            merge=True,
        )

        refreshed = post_ref.get()
        return self._to_admin_post(refreshed.id, refreshed.to_dict() or {})

    def delete_user(self, user_id: str) -> None:
        # 1) Delete from Firebase Auth (best-effort)
        try:
            firebase_auth = get_firebase_auth()
            firebase_auth.delete_user(user_id)
        except Exception:
            # Keep going: we still want to delete the Firestore doc.
            pass

        # 2) Delete Firestore user doc
        self._db.collection("users").document(user_id).delete()

    def set_user_banned(self, user_id: str, banned: bool) -> None:
        status = "banned" if banned else "active"

        # Update Firebase Auth user disabled flag (best-effort)
        try:
            firebase_auth = get_firebase_auth()
            firebase_auth.update_user(user_id, disabled=banned)
        except Exception:
            pass

        # Update Firestore user status
        self._db.collection("users").document(user_id).set({"status": status, "banned": banned}, merge=True)

    def set_profile_banned(self, profile_id: str, banned: bool) -> None:
        status = "banned" if banned else "active"
        self._db.collection("profiles").document(profile_id).set({"status": status, "banned": banned}, merge=True)

    def admin_analytics(self) -> AnalyticsDTO:
        now = datetime.now(timezone.utc)
        profiles = self.list_admin_profiles()
        posts = self.list_admin_posts()

        # users collection powers "signups" in the chart
        users = self._db.collection("users").limit(5000).stream()
        user_created_ats: list[str] = []
        users_total = 0
        for d in users:
            users_total += 1
            data = d.to_dict() or {}
            user_created_ats.append(_to_iso(data.get("createdAt") or data.get("CreatedAt")))

        totals = {
            "usersTotal": users_total,
            "profilesTotal": len(profiles),
            "postsTotal": len(posts),
        }

        series: list[SeriesPointDTO] = []
        day_buckets: dict[str, dict[str, int]] = {}
        for days_ago in range(6, -1, -1):
            day = (now - timedelta(days=days_ago)).date().isoformat()
            day_buckets[day] = {"users": 0, "posts": 0}

        for created_at in user_created_ats:
            day = _safe_day(created_at)
            if day in day_buckets:
                day_buckets[day]["users"] += 1

        for p in posts:
            day = _safe_day(p.createdAt)
            if day in day_buckets:
                day_buckets[day]["posts"] += 1

        for day, counts in day_buckets.items():
            series.append(SeriesPointDTO(day=day, users=counts["users"], posts=counts["posts"]))

        return AnalyticsDTO(
            generatedAt=_to_iso(now),
            totals=totals,
            series7d=series,
        )

    def _to_admin_post(self, post_id: str, data: dict[str, Any]) -> AdminPostDTO:
        moderation = data.get("moderation") if isinstance(data.get("moderation"), dict) else {}
        return AdminPostDTO(
            id=post_id,
            targetId=str(data.get("targetId") or ""),
            targetType=str(data.get("targetType") or ""),
            text=str(data.get("text") or ""),
            rating=_to_int(data.get("rating") if data.get("rating") is not None else data.get("Rating")),
            reports=_to_int(data.get("reports") or data.get("Reports") or data.get("reportCount") or 0),
            moderationStatus=_to_moderation_status(moderation.get("status")),
            moderationAllowed=bool(moderation.get("allowed") is True),
            moderationExplanation=_to_optional_str(moderation.get("explanation")),
            moderationViolations=_to_str_list(moderation.get("violations")),
            forcedByAdmin=bool(moderation.get("forcedByAdmin") is True),
            indexed=bool(data.get("indexed") is True),
            indexingVersion=_to_optional_int(data.get("indexing_version") or data.get("indexingVersion")),
            createdAt=_to_iso(data.get("createdAt") or data.get("CreatedAt")),
        )


def _to_iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, str) and value.strip():
        return value.strip()
    return datetime.now(timezone.utc).isoformat()


def _to_int(value: Any) -> int:
    try:
        if value is None:
            return 0
        if isinstance(value, bool):
            return int(value)
        return int(value)
    except Exception:
        return 0


def _to_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        if isinstance(value, bool):
            return float(int(value))
        return float(value)
    except Exception:
        return 0.0


def _safe_day(iso_or_str: str) -> str:
    # Accepts ISO strings and returns YYYY-MM-DD; fallback to "".
    try:
        return datetime.fromisoformat(iso_or_str.replace("Z", "+00:00")).date().isoformat()
    except Exception:
        return ""


def _to_status(status_value: Any, banned_value: Any) -> AdminStatusDTO:
    if isinstance(status_value, str):
        v = status_value.strip().lower()
        if v in ("active", "banned"):
            return v  # type: ignore[return-value]
    if banned_value is True:
        return "banned"
    return "active"


def _to_moderation_status(value: Any) -> str:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"pending", "approved", "rejected", "review"}:
            return normalized
    return "pending"


def _to_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _to_optional_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None
