from collections import defaultdict, deque
from datetime import date, datetime, timezone
import hashlib
import random
from typing import Any, cast

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.firestore import get_db
from app.jobs.tasks import process_post_task


router = APIRouter()


def get_db_client():
    return get_db()

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
        "message": "FastAPI is connected to Firestore"
    }


@router.get("/profiles")
def get_profiles():
    db = get_db_client()
    docs = db.collection("profiles").stream()
    profiles = []

    for doc in docs:
        profiles.append({
            "id": doc.id,
            **(doc.to_dict() or {})
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
            **(doc.to_dict() or {})
        })

    return JSONResponse(content=cafeterias, status_code=200)


@router.get("/posts")
def get_posts():
    db = get_db_client()
    docs = db.collection("posts").stream()
    posts = []

    for doc in docs:
        posts.append({
            "id": doc.id,
            **(doc.to_dict() or {})
        })

    return JSONResponse(content=posts, status_code=200)

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
        post_docs = db.collection("posts").limit(100).stream()
        posts = [{"id": d.id, "type": "post", **(d.to_dict() or {})} for d in post_docs]
        items += posts

    weights = {"profile": 3, "cafeteria": 2, "post": 2} if include_posts else {"profile": 3, "cafeteria": 2}

    mixed = build_mixed_feed(
        items,
        page_size=limit,
        weights=weights,
        max_streak=2,
        seed=seed
    )

    return JSONResponse(content=mixed, status_code=200)


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

    created_at = datetime.now(timezone.utc).isoformat()
    doc_ref = db.collection("posts").document()
    doc_ref.set(
        {
            **data,
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
