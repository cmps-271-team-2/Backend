from fastapi import APIRouter, Query, Request, HTTPException
from fastapi.responses import JSONResponse
from firebase_admin import firestore

from pydantic import BaseModel
from typing import Optional, Literal
from collections import defaultdict, deque
import random
from datetime import date

from app.core.firebase_admin import init_firebase_admin
from app.core.firestore import get_db

init_firebase_admin()
db = get_db()

router = APIRouter()


class ProfileCreate(BaseModel):
    type: str
    name: str


class CafeteriaCreate(BaseModel):
    name: str


class PostCreate(BaseModel):
    rating: int
    text: str
    targetId: str
    targetType: str


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
            **(doc.to_dict() or {})
        })

    return items


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
    return JSONResponse(content=profiles, status_code=200)


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
    return JSONResponse(content=cafeterias, status_code=200)


@router.get("/posts")
def get_posts(
    sort_by: str = Query("createdAt"),
    order: Literal["asc", "desc"] = Query("desc")
):
    posts = fetch_sorted_collection(
        collection_name="posts",
        allowed_sort_fields=["rating", "createdAt", "targetType"],
        sort_by=sort_by,
        order=order
    )
    return JSONResponse(content=posts, status_code=200)


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
    return JSONResponse(content=courses, status_code=200)


@router.get("/feed")
def get_feed(
    request: Request,
    limit: int = Query(20),
    user_id: str = Query("guest"),
    include_posts: bool = Query(True),
    sort_by: Optional[str] = Query(None),
    order: Literal["asc", "desc"] = Query("desc")
):
    seed = hash(f"{user_id}-{date.today().isoformat()}")

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

    reverse = (order == "desc")

    if sort_by == "rating":
        mixed.sort(key=lambda x: x.get("rating", 0), reverse=reverse)
    elif sort_by == "name":
        mixed.sort(key=lambda x: str(x.get("name", "")).lower(), reverse=reverse)

    return JSONResponse(content=mixed, status_code=200)


@router.post("/profiles")
async def create_profile(request: Request):
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
    try:
        data = await request.json()
    except Exception:
        data = None

    required_fields = ["rating", "text", "targetId", "targetType"]

    if not data or not all(field in data for field in required_fields):
        return JSONResponse(content={"error": "Missing required fields"}, status_code=400)

    doc_ref = db.collection("posts").document()
    doc_ref.set({
        "rating": data["rating"],
        "text": data["text"],
        "targetId": data["targetId"],
        "targetType": data["targetType"],
        "createdAt": firestore.SERVER_TIMESTAMP
    })

    return JSONResponse(content={"id": doc_ref.id}, status_code=201)