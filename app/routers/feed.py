from collections import defaultdict, deque
from datetime import date, datetime, timezone
import hashlib
import random
from typing import Any, cast

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.firebase_admin import get_firebase_auth
from app.core.firestore import get_db
from app.jobs.index_posts import fetch_relevant_posts
from app.jobs.tasks import process_post_task


router = APIRouter()

_MAX_RECOMMENDATION_PROMPT_CHARS = 2000


class LikeRequest(BaseModel):
    user_id: str


def get_db_client():
    return get_db()


def _normalize_text(value: Any, fallback: str) -> str:
    if isinstance(value, str):
        trimmed = value.strip()
        return trimmed or fallback

    if value is None:
        return fallback

    trimmed = str(value).strip()
    return trimmed or fallback


def _get_authenticated_user(request: Any) -> dict[str, Any] | None:
    headers = getattr(request, "headers", None)
    if headers is None:
        return None

    try:
        authorization = headers.get("authorization")
    except Exception:
        authorization = None

    if not authorization:
        return None

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    try:
        return get_firebase_auth().verify_id_token(parts[1].strip())
    except Exception:
        return None


def _resolve_user_snapshot(db, request: Any, payload: dict[str, Any]) -> dict[str, Any]:
    decoded_user = _get_authenticated_user(request) or {}
    user_id = _normalize_text(decoded_user.get("uid") or payload.get("userId"), "")

    user_ref = db.collection("users").document(user_id) if user_id else None
    user_data: dict[str, Any] = {}
    if user_ref is not None:
        snapshot = user_ref.get()
        if snapshot.exists:
            user_data = snapshot.to_dict() or {}

    display_name = _normalize_text(user_data.get("displayName"), "Student")
    major = _normalize_text(user_data.get("major"), "Unknown Major")
    show_display_name = bool(user_data.get("showDisplayName") is True)

    if user_ref is not None:
        user_ref.set(
            {
                "displayName": display_name,
                "major": major,
                "showDisplayName": show_display_name,
            },
            merge=True,
        )

    return {
        "userId": user_id,
        "displayName": display_name,
        "major": major,
        "showDisplayName": show_display_name,
    }


def _to_json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _to_json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_to_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)

# -------------------------------
# Feed Algorithm Helpers
# -------------------------------
def build_mixed_feed(items, page_size=20, weights=None, max_streak=2, seed=None):
    """
    Mixed randomized feed:
    - bucket by type
    - shuffle each bucket
    - weighted round-robin
    - anti-streak rule
    """
    if weights is None:
        weights = {"profile": 1, "cafeteria": 1, "post": 1}

    rng = random.Random(seed)

    # 1) Bucket items by type
    buckets = defaultdict(list)
    for it in items:
        t = it.get("type")
        if t in weights:
            buckets[t].append(it)

    # 2) Shuffle each bucket
    for t in buckets:
        rng.shuffle(buckets[t])

    # Convert to queues
    queues = {t: deque(buckets.get(t, [])) for t in weights.keys()}

    # 3) Build weighted pattern
    pattern = []
    for t, w in weights.items():
        pattern.extend([t] * max(0, int(w)))
    if not pattern:
        return []

    feed = []
    last_type = None
    streak = 0
    i = 0

    def any_left():
        return any(len(q) > 0 for q in queues.values())

    def pick_type(preferred):
        nonlocal last_type, streak

        def ok(t):
            if len(queues[t]) == 0:
                return False
            if last_type == t and streak >= max_streak:
                return False
            return True

        if ok(preferred):
            return preferred

        types = list(weights.keys())
        rng.shuffle(types)
        for t in types:
            if ok(t):
                return t

        for t in types:
            if len(queues[t]) > 0:
                return t

        return None

    # 4) Fill feed
    while len(feed) < page_size and any_left():
        preferred = pattern[i % len(pattern)]
        i += 1

        chosen = pick_type(preferred)
        if chosen is None:
            break

        item = queues[chosen].popleft()
        feed.append(item)

        if chosen == last_type:
            streak += 1
        else:
            last_type = chosen
            streak = 1

    return feed


# -------------------------------
# Routes
# -------------------------------
@router.get("/")
def home():
    return {
        "status": "ok",
        "message": "FastAPI is connected to Firestore",
    }


@router.get("/profiles")
def get_profiles():
    db = get_db_client()
    docs = db.collection("profiles").stream()
    profiles = []

    for doc in docs:
        profiles.append({
            "id": doc.id,
            **(doc.to_dict() or {}),
        })

    return JSONResponse(content=profiles, status_code=200)


@router.get("/cafeterias")
def get_cafeterias():
    db = get_db_client()
    docs = db.collection("cafeterias").stream()
    cafeterias = []

    for doc in docs:
        cafeterias.append({
            "id": doc.id,
            **(doc.to_dict() or {}),
        })

    return JSONResponse(content=cafeterias, status_code=200)


@router.get("/posts")
def get_posts():
    db = get_db_client()
    docs = db.collection("posts").stream()
    posts = []

    for doc in docs:
        raw_post = doc.to_dict() or {}
        posts.append({
            "id": doc.id,
            **_to_json_safe(raw_post)
        })

    approved_posts = [
        post for post in posts
        if post.get("moderation", {}).get("allowed") is True
    ]

    return JSONResponse(content=approved_posts, status_code=200)


# -------------------------------
# NEW: Mixed Random Feed Endpoint
# -------------------------------
@router.get("/feed")
def get_feed(request: Request):
    """
    Returns a mixed randomized feed from your collections.
    Query params:
      - limit
      - user_id
      - include_posts
    """
    db = get_db_client()

    limit = int(request.query_params.get("limit", 20))
    user_id = request.query_params.get("user_id", "guest")
    include_posts = request.query_params.get("include_posts", "1") == "1"

    # Stable "random" per user per day (so refresh doesn't reshuffle constantly)
    stable_key = f"{user_id}-{date.today().isoformat()}".encode("utf-8")
    seed = int.from_bytes(hashlib.sha256(stable_key).digest()[:8], "big", signed=False)

    prof_docs = db.collection("profiles").limit(100).stream()
    cafe_docs = db.collection("cafeterias").limit(100).stream()

    profiles = [{"id": d.id, "type": "profile", **(d.to_dict() or {})} for d in prof_docs]
    cafeterias = [{"id": d.id, "type": "cafeteria", **(d.to_dict() or {})} for d in cafe_docs]

    items = profiles + cafeterias

    if include_posts:
        recommendation_prompt: str | None = None
        if user_id != "guest":
            user_snapshot = db.collection("users").document(user_id).get()
            if user_snapshot.exists:
                user_data = user_snapshot.to_dict() or {}
                recommendation_prompt = user_data.get("recommendationPrompt") or None

        if recommendation_prompt:
            semantic_posts = fetch_relevant_posts(recommendation_prompt, limit=limit)
            posts: list[dict[str, Any]] = [{"type": "post", **_to_json_safe(p)} for p in semantic_posts]
        else:
            post_docs = db.collection("posts").limit(100).stream()
            posts = [{"id": d.id, "type": "post", **_to_json_safe(d.to_dict() or {})} for d in post_docs]

        items += posts

    weights = {"profile": 3, "cafeteria": 2, "post": 2} if include_posts else {"profile": 3, "cafeteria": 2}

    mixed = build_mixed_feed(
        items,
        page_size=limit,
        weights=weights,
        max_streak=2,
        seed=seed,
    )

    return JSONResponse(content=mixed, status_code=200)


# -------------------------------
# Like endpoint
# -------------------------------
@router.post("/posts/{post_id}/like")
async def like_post(post_id: str, body: LikeRequest):
    """
    Toggle a like on a post for the given user.
    Updates the user's recommendationPrompt in Firestore based on what they liked.
    """
    db = get_db_client()

    post_ref = db.collection("posts").document(post_id)
    post_snapshot = post_ref.get()
    if not post_snapshot.exists:
        return JSONResponse(content={"error": "Post not found"}, status_code=404)

    post_data = post_snapshot.to_dict() or {}
    liked_by: list[str] = list(post_data.get("likedBy") or [])

    if body.user_id in liked_by:
        liked_by.remove(body.user_id)
        liked = False
    else:
        liked_by.append(body.user_id)
        liked = True

    post_ref.set({"likedBy": liked_by, "likes": len(liked_by)}, merge=True)

    if liked:
        target_type = str(post_data.get("targetType") or "")
        target_id = str(post_data.get("targetId") or "")
        text = str(post_data.get("text") or "")
        snippet = f"{target_type} {target_id}: {text}".strip()

        user_ref = db.collection("users").document(body.user_id)
        user_snapshot = user_ref.get()
        existing_prompt: str = ""
        if user_snapshot.exists:
            existing_prompt = (user_snapshot.to_dict() or {}).get("recommendationPrompt") or ""

        new_prompt = (existing_prompt + "\n" + snippet).strip()
        if len(new_prompt) > _MAX_RECOMMENDATION_PROMPT_CHARS:
            lines = new_prompt.splitlines()
            while lines and len("\n".join(lines)) > _MAX_RECOMMENDATION_PROMPT_CHARS:
                lines.pop(0)
            new_prompt = "\n".join(lines)

        user_ref.set({"recommendationPrompt": new_prompt}, merge=True)

    return JSONResponse(content={"liked": liked, "likes": len(liked_by)}, status_code=200)


# -------------------------------
# Create endpoints
# -------------------------------
@router.post("/profiles")
async def create_profile(request: Request):
    db = get_db_client()
    try:
        data = await request.json()
    except Exception:
        data = None

    if not data or "type" not in data or "name" not in data:
        return JSONResponse(content={"error": "Missing required fields"}, status_code=400)

    doc_ref = db.collection("profiles").document()
    doc_ref.set(data)

    return JSONResponse(content={"id": doc_ref.id}, status_code=201)


@router.post("/cafeterias")
async def create_cafeteria(request: Request):
    db = get_db_client()
    try:
        data = await request.json()
    except Exception:
        data = None

    if not data or "name" not in data:
        return JSONResponse(content={"error": "Missing required field: name"}, status_code=400)

    doc_ref = db.collection("cafeterias").document()
    doc_ref.set(data)

    return JSONResponse(content={"id": doc_ref.id}, status_code=201)


@router.post("/posts")
async def create_post(request: Request):
    db = get_db_client()
    try:
        data = await request.json()
    except Exception:
        data = None

    required_fields = ["rating", "text", "targetId", "targetType"]

    if not data or not all(field in data for field in required_fields):
        return JSONResponse(content={"error": "Missing required fields"}, status_code=400)

    user_snapshot = _resolve_user_snapshot(db, request, cast(dict[str, Any], data))

    created_at = datetime.now(timezone.utc).isoformat()
    doc_ref = db.collection("posts").document()
    doc_ref.set(
        {
            **data,
            "userId": user_snapshot["userId"],
            "displayName": user_snapshot["displayName"],
            "major": user_snapshot["major"],
            "showDisplayName": user_snapshot["showDisplayName"],
            "createdAt": created_at,
            "moderation": {
                "status": "pending",
                "allowed": False,
                "violations": [],
                "explanation": "Moderation pending.",
                "model": None,
                "checkedAt": None,
            },
            "indexed": False,
        }
    )

    task = cast(Any, process_post_task).delay(doc_ref.id)

    return JSONResponse(
        content={
            "id": doc_ref.id,
            "status": "queued",
            "taskId": task.id,
            "moderation": {
                "status": "pending",
                "allowed": False,
            },
        },
        status_code=202,
    )
