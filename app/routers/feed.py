from collections import defaultdict, deque
from datetime import date, datetime, timezone
import hashlib
import random
from typing import Any, Optional, Literal, cast

from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
<<<<<<< HEAD
from firebase_admin import firestore
=======
>>>>>>> origin/main
from pydantic import BaseModel

from app.core.firestore import get_db
from app.jobs.index_posts import fetch_relevant_posts
from app.jobs.tasks import process_post_task

router = APIRouter()

_MAX_RECOMMENDATION_PROMPT_CHARS = 2000


class LikeRequest(BaseModel):
    user_id: str


class SpotCreate(BaseModel):
    name: str
    description: str = ""
    category: str
    location: str
    createdBy: str = "guest"
    rating: int = 0
    reviewCount: int = 0


def get_db_client():
    return get_db()


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


def _serialize_doc(doc) -> dict:
    return {
        "id": doc.id,
        **_to_json_safe(doc.to_dict() or {}),
    }


def fetch_sorted_collection(
    collection_name: str,
    allowed_sort_fields: list[str],
    sort_by: str,
    order: Literal["asc", "desc"],
):
    db = get_db_client()

    if sort_by not in allowed_sort_fields:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sort_by. Allowed fields: {allowed_sort_fields}",
        )

    if order not in ["asc", "desc"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid order. Use 'asc' or 'desc'",
        )

    direction = (
        firestore.Query.ASCENDING
        if order == "asc"
        else firestore.Query.DESCENDING
    )

    docs = db.collection(collection_name).order_by(
        sort_by,
        direction=direction,
    ).stream()

    return [_serialize_doc(doc) for doc in docs]


def build_mixed_feed(items, page_size=20, weights=None, max_streak=2, seed=None):
    if weights is None:
        weights = {"profile": 1, "cafeteria": 1, "spot": 1, "post": 1}

    rng = random.Random(seed)

    buckets = defaultdict(list)
    for it in items:
        t = it.get("type")
        if t in weights:
            buckets[t].append(it)

    for t in buckets:
        rng.shuffle(buckets[t])

    queues = {t: deque(buckets.get(t, [])) for t in weights.keys()}

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


def _matches_search(item: dict, query: str) -> bool:
    q = query.strip().lower()
    return (
        q in str(item.get("name", "")).lower()
        or q in str(item.get("description", "")).lower()
        or q in str(item.get("location", "")).lower()
        or q in str(item.get("category", "")).lower()
        or q in str(item.get("text", "")).lower()
        or q in str(item.get("title", "")).lower()
        or q in str(item.get("code", "")).lower()
        or q in str(item.get("targetType", "")).lower()
    )


@router.get("/")
def home():
    return {
        "status": "ok",
        "message": "FastAPI is connected to Firestore",
    }


@router.get("/profiles")
def get_profiles(
    sort_by: str = Query("name"),
    order: Literal["asc", "desc"] = Query("asc"),
):
    profiles = fetch_sorted_collection(
        collection_name="profiles",
        allowed_sort_fields=["name", "type"],
        sort_by=sort_by,
        order=order,
    )
    return JSONResponse(content=jsonable_encoder(profiles), status_code=200)


@router.get("/cafeterias")
def get_cafeterias(
    sort_by: str = Query("name"),
    order: Literal["asc", "desc"] = Query("asc"),
):
    cafeterias = fetch_sorted_collection(
        collection_name="cafeterias",
        allowed_sort_fields=["name"],
        sort_by=sort_by,
        order=order,
    )
    return JSONResponse(content=jsonable_encoder(cafeterias), status_code=200)


@router.get("/courses")
def get_courses(
    sort_by: str = Query("code"),
    order: Literal["asc", "desc"] = Query("asc"),
):
    courses = fetch_sorted_collection(
        collection_name="courses",
        allowed_sort_fields=[
            "code",
            "title",
            "department",
            "number",
            "ratingAvg",
            "ratingCount",
        ],
        sort_by=sort_by,
        order=order,
    )
    return JSONResponse(content=jsonable_encoder(courses), status_code=200)


@router.get("/posts")
def get_posts(
    sort_by: str = Query("createdAt"),
    order: Literal["asc", "desc"] = Query("desc"),
):
    posts = fetch_sorted_collection(
        collection_name="posts",
        allowed_sort_fields=["rating", "createdAt", "targetType"],
        sort_by=sort_by,
        order=order,
    )
    return JSONResponse(content=jsonable_encoder(posts), status_code=200)


@router.get("/spots")
def get_spots(
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    sort_by: Literal["name", "category", "location", "rating", "createdAt"] = Query("createdAt"),
    order: Literal["asc", "desc"] = Query("desc"),
):
    db = get_db_client()
    docs = db.collection("spots").stream()
    spots = []

    for doc in docs:
        spot = {
            "id": doc.id,
            "type": "spot",
            **_to_json_safe(doc.to_dict() or {}),
        }
        spots.append(spot)

    if category:
        category = category.strip().lower()
        if category not in ["study", "food"]:
            raise HTTPException(
                status_code=400,
                detail="category must be either 'study' or 'food'",
            )
        spots = [
            s for s in spots
            if str(s.get("category", "")).lower() == category
        ]

    if search:
        spots = [s for s in spots if _matches_search(s, search)]

    reverse = (order == "desc")

    if sort_by == "rating":
        spots.sort(key=lambda x: x.get("rating", 0), reverse=reverse)
    else:
        spots.sort(key=lambda x: str(x.get(sort_by, "")), reverse=reverse)

    return JSONResponse(content=jsonable_encoder(spots), status_code=200)


@router.get("/feed")
def get_feed(
    limit: int = Query(20),
    user_id: str = Query("guest"),
    include_posts: bool = Query(True),
    sort_by: Optional[str] = Query(None),
    order: Literal["asc", "desc"] = Query("desc"),
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
):
    db = get_db_client()

    stable_key = f"{user_id}-{date.today().isoformat()}".encode("utf-8")
    seed = int.from_bytes(
        hashlib.sha256(stable_key).digest()[:8],
        "big",
        signed=False,
    )

    prof_docs = db.collection("profiles").limit(100).stream()
    cafe_docs = db.collection("cafeterias").limit(100).stream()
    spot_docs = db.collection("spots").limit(100).stream()

    profiles = [
        {"id": d.id, "type": "profile", **_to_json_safe(d.to_dict() or {})}
        for d in prof_docs
    ]
    cafeterias = [
        {"id": d.id, "type": "cafeteria", **_to_json_safe(d.to_dict() or {})}
        for d in cafe_docs
    ]
    spots = [
        {"id": d.id, "type": "spot", **_to_json_safe(d.to_dict() or {})}
        for d in spot_docs
    ]

    items = profiles + cafeterias + spots

    if include_posts:
<<<<<<< HEAD
        post_docs = db.collection("posts").limit(100).stream()
        posts = [
            {"id": d.id, "type": "post", **_to_json_safe(d.to_dict() or {})}
            for d in post_docs
        ]
=======
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

>>>>>>> origin/main
        items += posts

    if category:
        category = category.strip().lower()
        if category not in ["study", "food"]:
            raise HTTPException(
                status_code=400,
                detail="category must be either 'study' or 'food'",
            )
        items = [
            item for item in items
            if str(item.get("category", "")).lower() == category
        ]

    if search:
        items = [item for item in items if _matches_search(item, search)]

    weights = (
        {"profile": 3, "cafeteria": 2, "spot": 2, "post": 2}
        if include_posts
        else {"profile": 3, "cafeteria": 2, "spot": 2}
    )

    mixed = build_mixed_feed(
        items,
        page_size=limit,
        weights=weights,
        max_streak=2,
        seed=seed,
    )

    reverse = (order == "desc")

    if sort_by == "rating":
        mixed.sort(key=lambda x: x.get("rating", 0), reverse=reverse)
    elif sort_by == "createdAt":
        mixed.sort(key=lambda x: str(x.get("createdAt") or ""), reverse=reverse)

    return JSONResponse(content=jsonable_encoder(mixed), status_code=200)


<<<<<<< HEAD
=======
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
>>>>>>> origin/main
@router.post("/profiles")
async def create_profile(request: Request):
    db = get_db_client()

    try:
        data = await request.json()
    except Exception:
        data = None

    if not data or "type" not in data or "name" not in data:
        return JSONResponse(
            content={"error": "Missing required fields"},
            status_code=400,
        )

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
        return JSONResponse(
            content={"error": "Missing required field: name"},
            status_code=400,
        )

    doc_ref = db.collection("cafeterias").document()
    doc_ref.set(data)

    return JSONResponse(content={"id": doc_ref.id}, status_code=201)


@router.post("/spots")
async def create_spot(data: SpotCreate):
    db = get_db_client()

    category = data.category.strip().lower()
    if category not in ["study", "food"]:
        return JSONResponse(
            content={"error": "category must be either 'study' or 'food'"},
            status_code=400,
        )

    doc_ref = db.collection("spots").document()
    doc_ref.set({
        "name": data.name,
        "description": data.description,
        "category": category,
        "location": data.location,
        "createdBy": data.createdBy,
        "rating": data.rating,
        "reviewCount": data.reviewCount,
        "createdAt": datetime.now(timezone.utc),
    })

    return JSONResponse(
        content={"id": doc_ref.id, "message": "Spot created successfully"},
        status_code=201,
    )


@router.post("/posts")
async def create_post(request: Request):
    db = get_db_client()

    try:
        data = await request.json()
    except Exception:
        data = None

    required_fields = ["rating", "text", "targetId", "targetType"]

    if not data or not all(field in data for field in required_fields):
        return JSONResponse(
            content={"error": "Missing required fields"},
            status_code=400,
        )

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