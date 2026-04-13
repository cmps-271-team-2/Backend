from fastapi import APIRouter, Query, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from firebase_admin import firestore

from typing import Optional, Literal
from collections import defaultdict, deque
import random
import hashlib
from datetime import date, datetime, timezone

from app.core.firebase_admin import get_firebase_auth
from app.core.firestore import get_db

router = APIRouter()


def get_db_client():
    return get_db()


def to_json_safe(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): to_json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [to_json_safe(v) for v in value]
    return value


def _is_post_visible(post: dict) -> bool:
    """Return True only when a post has been indexed AND approved by moderation."""
    if not post.get("indexed"):
        return False
    moderation = post.get("moderation") or {}
    if isinstance(moderation, dict):
        return str(moderation.get("status") or "").strip().lower() == "approved"
    return False


def _normalize_text(value, fallback: str) -> str:
    if isinstance(value, str):
        trimmed = value.strip()
        return trimmed or fallback

    if value is None:
        return fallback

    trimmed = str(value).strip()
    return trimmed or fallback


def _get_authenticated_user(request):
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


def _resolve_user_snapshot(db_client, request, payload: dict) -> dict:
    decoded_user = _get_authenticated_user(request) or {}
    user_id = _normalize_text(decoded_user.get("uid") or payload.get("userId"), "")

    user_ref = db_client.collection("users").document(user_id) if user_id else None
    user_data = {}
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


def fetch_sorted_collection(collection_name, allowed_sort_fields, sort_by, order):
    db = get_db_client()

    if sort_by not in allowed_sort_fields:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sort_by. Allowed fields: {allowed_sort_fields}"
        )

    if order not in ["asc", "desc"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid order. Use 'asc' or 'desc'"
        )

    direction = (
        firestore.Query.ASCENDING
        if order == "asc"
        else firestore.Query.DESCENDING
    )

    docs = db.collection(collection_name).order_by(
        sort_by, direction=direction
    ).stream()

    items = []
    for doc in docs:
        items.append({
            "id": doc.id,
            **to_json_safe(doc.to_dict() or {})
        })

    return items


def matches_search(item, query: str) -> bool:
    q = query.strip().lower()
    return (
        q in str(item.get("name", "")).lower()
        or q in str(item.get("description", "")).lower()
        or q in str(item.get("location", "")).lower()
        or q in str(item.get("category", "")).lower()
        or q in str(item.get("text", "")).lower()
        or q in str(item.get("title", "")).lower()
        or q in str(item.get("code", "")).lower()
    )


@router.get("/")
def home():
    return {
        "status": "ok",
        "message": "FastAPI is connected to Firestore"
    }


@router.get("/profiles")
def get_profiles(
    sort_by: str = Query("name"),
    order: Literal["asc", "desc"] = Query("asc")
):
    profiles = fetch_sorted_collection(
        collection_name="profiles",
        allowed_sort_fields=["name", "type"],
        sort_by=sort_by,
        order=order
    )
    return JSONResponse(content=jsonable_encoder(profiles), status_code=200)


@router.get("/cafeterias")
def get_cafeterias(
    sort_by: str = Query("name"),
    order: Literal["asc", "desc"] = Query("asc")
):
    cafeterias = fetch_sorted_collection(
        collection_name="cafeterias",
        allowed_sort_fields=["name"],
        sort_by=sort_by,
        order=order
    )
    return JSONResponse(content=jsonable_encoder(cafeterias), status_code=200)


@router.get("/posts")
def get_posts(
    sort_by: str = Query("createdAt"),
    order: Literal["asc", "desc"] = Query("desc")
):
    posts = [
        p for p in fetch_sorted_collection(
            collection_name="posts",
            allowed_sort_fields=["rating", "createdAt", "targetType"],
            sort_by=sort_by,
            order=order
        )
        if _is_post_visible(p)
    ]
    return JSONResponse(content=jsonable_encoder(posts), status_code=200)


@router.get("/courses")
def get_courses(
    sort_by: str = Query("code"),
    order: Literal["asc", "desc"] = Query("asc")
):
    courses = fetch_sorted_collection(
        collection_name="courses",
        allowed_sort_fields=["code", "title", "department", "number", "ratingAvg", "ratingCount"],
        sort_by=sort_by,
        order=order
    )
    return JSONResponse(content=jsonable_encoder(courses), status_code=200)


@router.get("/spots")
def get_spots(
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    sort_by: Literal["name", "category", "location", "rating", "createdAt"] = Query("createdAt"),
    order: Literal["asc", "desc"] = Query("desc")
):
    db = get_db_client()
    docs = db.collection("spots").stream()
    spots = []

    for doc in docs:
        spots.append({
            "id": doc.id,
            "type": "spot",
            **to_json_safe(doc.to_dict() or {})
        })

    if category:
        category = category.strip().lower()
        if category not in ["study", "food"]:
            raise HTTPException(
                status_code=400,
                detail="category must be either 'study' or 'food'"
            )
        spots = [
            s for s in spots
            if str(s.get("category", "")).lower() == category
        ]

    if search:
        spots = [s for s in spots if matches_search(s, search)]

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
    category: Optional[str] = Query(None)
):
    db = get_db_client()

    stable_key = f"{user_id}-{date.today().isoformat()}".encode("utf-8")
    seed = int.from_bytes(hashlib.sha256(stable_key).digest()[:8], "big", signed=False)

    prof_docs = db.collection("profiles").limit(100).stream()
    cafe_docs = db.collection("cafeterias").limit(100).stream()
    spot_docs = db.collection("spots").limit(100).stream()

    profiles = [{"id": d.id, "type": "profile", **to_json_safe(d.to_dict() or {})} for d in prof_docs]
    cafeterias = [{"id": d.id, "type": "cafeteria", **to_json_safe(d.to_dict() or {})} for d in cafe_docs]
    spots = [{"id": d.id, "type": "spot", **to_json_safe(d.to_dict() or {})} for d in spot_docs]

    items = profiles + cafeterias + spots

    if include_posts:
        post_docs = db.collection("posts").limit(100).stream()
        posts = [
            {"id": d.id, "type": "post", **to_json_safe(d.to_dict() or {})}
            for d in post_docs
            if _is_post_visible(d.to_dict() or {})
        ]
        items += posts

    if category:
        category = category.strip().lower()
        if category not in ["study", "food"]:
            raise HTTPException(
                status_code=400,
                detail="category must be either 'study' or 'food'"
            )
        items = [
            item for item in items
            if str(item.get("category", "")).lower() == category
        ]

    if search:
        items = [item for item in items if matches_search(item, search)]

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
        seed=seed
    )

    reverse = (order == "desc")

    if sort_by == "rating":
        mixed.sort(key=lambda x: x.get("rating", 0), reverse=reverse)
    elif sort_by == "createdAt":
        mixed.sort(key=lambda x: str(x.get("createdAt") or ""), reverse=reverse)

    return JSONResponse(content=jsonable_encoder(mixed), status_code=200)


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


@router.post("/spots")
async def create_spot(request: Request):
    db = get_db_client()

    try:
        data = await request.json()
    except Exception:
        data = None

    required_fields = ["name", "category", "location"]

    if not data or not all(field in data for field in required_fields):
        return JSONResponse(
            content={"error": "Missing required fields: name, category, location"},
            status_code=400
        )

    category = str(data["category"]).strip().lower()
    if category not in ["study", "food"]:
        return JSONResponse(
            content={"error": "category must be either 'study' or 'food'"},
            status_code=400
        )

    doc_ref = db.collection("spots").document()
    doc_ref.set({
        "name": data["name"],
        "description": data.get("description", ""),
        "category": category,
        "location": data["location"],
        "createdBy": data.get("createdBy", "guest"),
        "rating": data.get("rating", 0),
        "reviewCount": data.get("reviewCount", 0),
        "createdAt": datetime.now(timezone.utc),
    })

    return JSONResponse(
        content={"id": doc_ref.id, "message": "Spot created successfully"},
        status_code=201
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
        return JSONResponse(content={"error": "Missing required fields"}, status_code=400)

    user_snapshot = _resolve_user_snapshot(db, request, data)

    doc_ref = db.collection("posts").document()
    doc_ref.set({
        "rating": data["rating"],
        "text": data["text"],
        "targetId": data["targetId"],
        "targetType": data["targetType"],
        "userId": user_snapshot["userId"],
        "displayName": user_snapshot["displayName"],
        "major": user_snapshot["major"],
        "showDisplayName": user_snapshot["showDisplayName"],
        "createdAt": firestore.SERVER_TIMESTAMP
    })

    return JSONResponse(content={"id": doc_ref.id}, status_code=201)