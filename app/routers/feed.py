from fastapi import APIRouter, Depends, Header, Query, HTTPException
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from firebase_admin import firestore
from pydantic import BaseModel

from typing import Any, Optional, Literal
from collections import defaultdict, deque
import random
import hashlib
from datetime import date, datetime, timezone

from app.core.firestore import get_db
from app.core.firebase_admin import get_firebase_auth
from app.jobs.tasks import process_post_task
from app.routers.auth import get_current_user

router = APIRouter()


class SpotCreate(BaseModel):
    name: str
    category: Literal["study", "food"]
    location: str
    description: str = ""
    createdBy: str = "guest"
    openNow: bool = True

    spotType: Optional[str] = None
    noiseLevel: Optional[str] = None
    hasWifi: Optional[bool] = None
    hasOutlets: Optional[bool] = None

    venueCategory: Optional[str] = None
    priceLevel: Optional[str] = None


class PostCreate(BaseModel):
    rating: int
    text: str
    targetType: Literal["profile", "professor", "cafeteria", "course", "spot"]
    targetId: Optional[str] = None
    createdBy: str = "guest"
    userId: Optional[str] = None
    displayName: Optional[str] = None
    major: Optional[str] = None
    showDisplayName: Optional[bool] = None

    title: Optional[str] = None
    courseCode: Optional[str] = None
    courseName: Optional[str] = None
    professorName: Optional[str] = None
    department: Optional[str] = None
    semesterTaken: Optional[str] = None
    location: Optional[str] = None
    priceRange: Optional[str] = None
    bestTimeToGo: Optional[str] = None
    category: Optional[str] = None
    attendanceMandatory: Optional[bool] = None
    wouldRecommend: Optional[bool] = None
    attributes: Optional[list[str]] = None

    targetName: Optional[str] = None
    targetCategory: Optional[str] = None
    targetLocation: Optional[str] = None
    targetDescription: str = ""

    openNow: Optional[bool] = True
    spotType: Optional[str] = None
    noiseLevel: Optional[str] = None
    hasWifi: Optional[bool] = None
    hasOutlets: Optional[bool] = None
    venueCategory: Optional[str] = None
    priceLevel: Optional[str] = None


class ReactionRequest(BaseModel):
    type: Literal["like", "dislike"]


class FavoriteCreate(BaseModel):
    targetType: Literal["professor", "course", "spot", "post"]
    targetId: str
    targetName: str


class PostReportCreate(BaseModel):
    text: str


class SpotReportCreate(BaseModel):
    text: str


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
        return {str(k): to_json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [to_json_safe(v) for v in value]
    return value


def to_json_safe(value: Any) -> Any:
    return _to_json_safe(value)


def normalize_text(value: str) -> str:
    return " ".join(str(value).strip().lower().split())


def _get_optional_uid(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    try:
        decoded = get_firebase_auth().verify_id_token(parts[1].strip())
    except Exception:
        return None

    uid = decoded.get("uid") if isinstance(decoded, dict) else None
    if isinstance(uid, str) and uid.strip():
        return uid.strip()
    return None


def _favorite_doc_id(user_id: str, target_type: str, target_id: str) -> str:
    stable = f"{user_id}|{target_type}|{target_id}".encode("utf-8")
    return hashlib.sha1(stable).hexdigest()


def _resolve_post_author_fields(db, payload: PostCreate) -> dict:
    uid = (payload.userId or payload.createdBy or "").strip()

    display_name = (payload.displayName or "").strip() or "Student"
    major = (payload.major or "").strip() or "Unknown Major"
    show_display_name = bool(payload.showDisplayName is True)

    if uid and uid.lower() != "guest":
        user_snapshot = db.collection("users").document(uid).get()
        if user_snapshot.exists:
            user_data = user_snapshot.to_dict() or {}
            next_name = str(user_data.get("displayName") or "").strip()
            next_major = str(user_data.get("major") or "").strip()
            display_name = next_name or display_name
            major = next_major or major
            show_display_name = bool(user_data.get("showDisplayName") is True)

    return {
        "userId": uid or payload.createdBy,
        "displayName": display_name,
        "major": major,
        "showDisplayName": show_display_name,
    }


def _get_user_post_metadata(db, uid: Optional[str], post_items: list[dict]) -> tuple[set[str], set[str], set[str]]:
    if not uid or not post_items:
        return set(), set(), set()

    liked_ids: set[str] = set()
    disliked_ids: set[str] = set()
    for post in post_items:
        post_id = str(post.get("id") or "").strip()
        if not post_id:
            continue

        liked_by = post.get("likedBy") or []
        disliked_by = post.get("dislikedBy") or []

        if isinstance(liked_by, list) and uid in liked_by:
            liked_ids.add(post_id)
        if isinstance(disliked_by, list) and uid in disliked_by:
            disliked_ids.add(post_id)

    favorite_ids: set[str] = set()
    favorite_docs = db.collection("favorites").where("userId", "==", uid).where("targetType", "==", "post").stream()
    for doc in favorite_docs:
        data = doc.to_dict() or {}
        target_id = str(data.get("targetId") or "").strip()
        if target_id:
            favorite_ids.add(target_id)

    return liked_ids, disliked_ids, favorite_ids


def _attach_post_metadata(posts: list[dict], uid: Optional[str], liked_ids: set[str], disliked_ids: set[str], favorite_ids: set[str]) -> list[dict]:
    next_posts: list[dict] = []
    for post in posts:
        post_id = str(post.get("id") or "").strip()
        liked_by = post.get("likedBy")
        disliked_by = post.get("dislikedBy")

        likes = int(post.get("likes") or 0)
        dislikes = int(post.get("dislikes") or 0)
        if isinstance(liked_by, list):
            likes = len(liked_by)
        if isinstance(disliked_by, list):
            dislikes = len(disliked_by)

        current_user_reaction = None
        if post_id and post_id in liked_ids:
            current_user_reaction = "liked"
        elif post_id and post_id in disliked_ids:
            current_user_reaction = "disliked"

        owner_uid = str(post.get("userId") or post.get("createdBy") or "").strip()
        is_owner = bool(uid and owner_uid and uid == owner_uid)

        next_posts.append(
            {
                **post,
                "likes": likes,
                "dislikes": dislikes,
                "currentUserReaction": current_user_reaction,
                "isFavorited": bool(post_id and post_id in favorite_ids),
                "isOwner": is_owner,
            }
        )

    return next_posts


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
        or q in str(item.get("department", "")).lower()
    )


def find_existing_spot(db, name: str, category: str, location: str):
    name_key = normalize_text(name)
    category_key = normalize_text(category)
    location_key = normalize_text(location)

    docs = (
        db.collection("spots")
        .where("nameKey", "==", name_key)
        .where("category", "==", category_key)
        .where("locationKey", "==", location_key)
        .limit(1)
        .stream()
    )

    docs = list(docs)
    return docs[0] if docs else None


def get_or_create_spot(
    db,
    name: str,
    category: str,
    location: str,
    description: str = "",
    created_by: str = "guest",
    extra_fields: Optional[dict] = None,
):
    category = normalize_text(category)
    if category not in ["study", "food"]:
        raise HTTPException(
            status_code=400,
            detail="category must be either 'study' or 'food'"
        )

    existing_doc = find_existing_spot(db, name, category, location)
    if existing_doc:
        return existing_doc.id, False

    payload = {
        "name": name.strip(),
        "nameKey": normalize_text(name),
        "description": description.strip(),
        "category": category,
        "location": location.strip(),
        "locationKey": normalize_text(location),
        "createdBy": created_by,
        "rating": 0,
        "reviewCount": 0,
        "createdAt": datetime.now(timezone.utc),
    }

    if extra_fields:
        for key, value in extra_fields.items():
            if value is not None:
                payload[key] = value

    doc_ref = db.collection("spots").document()
    doc_ref.set(payload)

    return doc_ref.id, True


def update_spot_rating_summary(db, spot_id: str):
    posts = list(
        db.collection("posts")
        .where("targetType", "==", "spot")
        .where("targetId", "==", spot_id)
        .stream()
    )

    ratings = []
    for post in posts:
        data = post.to_dict() or {}
        rating = data.get("rating")
        if isinstance(rating, (int, float)):
            ratings.append(float(rating))

    review_count = len(ratings)
    avg_rating = round(sum(ratings) / review_count, 2) if review_count > 0 else 0

    db.collection("spots").document(spot_id).update({
        "rating": avg_rating,
        "reviewCount": review_count,
        "updatedAt": datetime.now(timezone.utc),
    })


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


@router.get("/professors")
def get_professors(
    search: Optional[str] = Query(None),
    sort_by: Literal["name", "department"] = Query("name"),
    order: Literal["asc", "desc"] = Query("asc")
):
    db = get_db_client()
    docs = db.collection("professors").stream()

    professors = []
    for doc in docs:
        professor = {
            "id": doc.id,
            "type": "profile",
            **to_json_safe(doc.to_dict() or {})
        }
        professors.append(professor)

    if search:
        professors = [p for p in professors if matches_search(p, search)]

    reverse = (order == "desc")
    professors.sort(key=lambda x: str(x.get(sort_by, "")), reverse=reverse)

    return JSONResponse(content=jsonable_encoder(professors), status_code=200)


@router.get("/professors/{prof_id}")
def get_professor_by_id(prof_id: str):
    db = get_db_client()
    doc = db.collection("professors").document(prof_id).get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Professor not found")

    professor = {
        "id": doc.id,
        "type": "profile",
        **to_json_safe(doc.to_dict() or {})
    }

    return JSONResponse(content=jsonable_encoder(professor), status_code=200)


@router.get("/professors/{prof_id}/posts")
def get_professor_posts(
    prof_id: str,
    sort_by: Literal["createdAt", "rating"] = Query("createdAt"),
    order: Literal["asc", "desc"] = Query("desc")
):
    db = get_db_client()

    docs = db.collection("posts") \
        .where("targetType", "==", "profile") \
        .where("targetId", "==", prof_id) \
        .stream()

    posts = []
    for doc in docs:
        posts.append({
            "id": doc.id,
            **to_json_safe(doc.to_dict() or {})
        })

    reverse = (order == "desc")
    if sort_by == "rating":
        posts.sort(key=lambda x: x.get("rating", 0), reverse=reverse)
    else:
        posts.sort(key=lambda x: str(x.get("createdAt", "")), reverse=reverse)

    return JSONResponse(content=jsonable_encoder(posts), status_code=200)


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
    order: Literal["asc", "desc"] = Query("desc"),
    indexed_only: bool = Query(True),
    search: Optional[str] = Query(None),
    authorization: Optional[str] = Header(default=None),
):
    posts = fetch_sorted_collection(
        collection_name="posts",
        allowed_sort_fields=["rating", "createdAt", "targetType"],
        sort_by=sort_by,
        order=order
    )
    if indexed_only:
        posts = [p for p in posts if p.get("indexed") is True]

    if search:
        posts = [p for p in posts if matches_search(p, search)]

    uid = _get_optional_uid(authorization)
    db = get_db_client()
    liked_ids, disliked_ids, favorite_ids = _get_user_post_metadata(db, uid, posts)
    posts = _attach_post_metadata(posts, uid, liked_ids, disliked_ids, favorite_ids)

    return JSONResponse(content=jsonable_encoder(posts), status_code=200)


@router.get("/posts/mine")
def get_my_posts(current_user: dict = Depends(get_current_user)):
    uid = current_user.get("uid", "")
    db = get_db_client()
    docs = db.collection("posts").where("userId", "==", uid).stream()
    posts = [{"id": doc.id, **to_json_safe(doc.to_dict() or {})} for doc in docs]
    if not posts:
        # also try createdBy field as a fallback
        docs2 = db.collection("posts").where("createdBy", "==", uid).stream()
        seen_ids = {p["id"] for p in posts}
        for doc in docs2:
            if doc.id not in seen_ids:
                posts.append({"id": doc.id, **to_json_safe(doc.to_dict() or {})})
    posts.sort(key=lambda p: p.get("createdAt") or "", reverse=True)
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
    category: Optional[str] = Query(None),
    authorization: Optional[str] = Header(default=None),
):
    db = get_db_client()

    stable_key = f"{user_id}-{date.today().isoformat()}".encode("utf-8")
    seed = int.from_bytes(hashlib.sha256(stable_key).digest()[:8], "big", signed=False)

    prof_docs = db.collection("professors").limit(100).stream()
    cafe_docs = db.collection("cafeterias").limit(100).stream()
    spot_docs = db.collection("spots").limit(100).stream()

    profiles = [{"id": d.id, "type": "profile", **to_json_safe(d.to_dict() or {})} for d in prof_docs]
    cafeterias = [{"id": d.id, "type": "cafeteria", **to_json_safe(d.to_dict() or {})} for d in cafe_docs]
    spots = [{"id": d.id, "type": "spot", **to_json_safe(d.to_dict() or {})} for d in spot_docs]

    items = profiles + cafeterias + spots

    if include_posts:
        post_docs = db.collection("posts").limit(100).stream()
        posts = [{"id": d.id, "type": "post", **to_json_safe(d.to_dict() or {})} for d in post_docs]
        uid = _get_optional_uid(authorization)
        liked_ids, disliked_ids, favorite_ids = _get_user_post_metadata(db, uid, posts)
        posts = _attach_post_metadata(posts, uid, liked_ids, disliked_ids, favorite_ids)
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
async def create_profile(data: dict):
    db = get_db_client()

    if not data or "type" not in data or "name" not in data:
        return JSONResponse(content={"error": "Missing required fields"}, status_code=400)

    doc_ref = db.collection("profiles").document()
    doc_ref.set(data)

    return JSONResponse(content={"id": doc_ref.id}, status_code=201)


@router.post("/cafeterias")
async def create_cafeteria(data: dict):
    db = get_db_client()

    if not data or "name" not in data:
        return JSONResponse(content={"error": "Missing required field: name"}, status_code=400)

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
            status_code=400
        )

    extra_fields = {
        "openNow": data.openNow,
        "spotType": data.spotType,
        "noiseLevel": data.noiseLevel,
        "hasWifi": data.hasWifi,
        "hasOutlets": data.hasOutlets,
        "venueCategory": data.venueCategory,
        "priceLevel": data.priceLevel,
    }

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
    spot_id, created = get_or_create_spot(
        db=db,
        name=data.name,
        category=category,
        location=data.location,
        description=data.description,
        created_by=data.createdBy,
        extra_fields=extra_fields,
    )

    if created:
        return JSONResponse(
            content={
                "id": spot_id,
                "message": "Spot created successfully",
                "created": True
            },
            status_code=201
        )

    return JSONResponse(
        content={
            "id": spot_id,
            "message": "Spot already exists",
            "created": False
        },
        status_code=200
    )


@router.post("/posts")
async def create_post(data: PostCreate):
    db = get_db_client()

    target_type = data.targetType.strip().lower()
    if target_type not in ["profile", "professor", "cafeteria", "course", "spot"]:
        return JSONResponse(
            content={"error": "Invalid targetType"},
            status_code=400
        )

    target_id = data.targetId

    if target_type == "spot":
        if not target_id:
            if not data.targetName or not data.targetCategory or not data.targetLocation:
                return JSONResponse(
                    content={
                        "error": "For new spot posts, provide targetName, targetCategory, and targetLocation"
                    },
                    status_code=400
                )

            target_id, _ = get_or_create_spot(
                db=db,
                name=data.targetName,
                category=data.targetCategory,
                location=data.targetLocation,
                description=data.targetDescription,
                created_by=data.createdBy,
                extra_fields={
                    "openNow": data.openNow,
                    "spotType": data.spotType,
                    "noiseLevel": data.noiseLevel,
                    "hasWifi": data.hasWifi,
                    "hasOutlets": data.hasOutlets,
                    "venueCategory": data.venueCategory,
                    "priceLevel": data.priceLevel,
                },
            )
    else:
        if not target_id:
            return JSONResponse(
                content={"error": "targetId is required for non-spot posts"},
                status_code=400
            )

    author_fields = _resolve_post_author_fields(db, data)

    post_payload = {
        "rating": data.rating,
        "text": data.text,
        "targetId": target_id,
        "targetType": target_type,
        "createdBy": data.createdBy,
        **author_fields,
        "likes": 0,
        "dislikes": 0,
        "likedBy": [],
        "dislikedBy": [],
        "createdAt": datetime.now(timezone.utc).isoformat()
    }

    optional_fields = {
        "title": data.title,
        "courseCode": data.courseCode,
        "courseName": data.courseName,
        "professorName": data.professorName,
        "department": data.department,
        "semesterTaken": data.semesterTaken,
        "location": data.location,
        "priceRange": data.priceRange,
        "bestTimeToGo": data.bestTimeToGo,
        "category": data.category,
        "attendanceMandatory": data.attendanceMandatory,
        "wouldRecommend": data.wouldRecommend,
    }

    for key, value in optional_fields.items():
        if value is not None:
            post_payload[key] = value

    if data.attributes:
        post_payload["attributes"] = [str(item).strip() for item in data.attributes if str(item).strip()]

    doc_ref = db.collection("posts").document()
    doc_ref.set(post_payload)

    if target_type == "spot":
        update_spot_rating_summary(db, target_id)

    task = process_post_task.delay(doc_ref.id)

    return JSONResponse(
        content={
            "id": doc_ref.id,
            "taskId": task.id,
            "targetId": target_id,
            "targetType": target_type
        },
        status_code=202
    )


@router.post("/posts/{post_id}/reaction")
def set_post_reaction(post_id: str, body: ReactionRequest, current_user: dict = Depends(get_current_user)):
    uid = str(current_user.get("uid") or "").strip()
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid user.")

    db = get_db_client()
    post_ref = db.collection("posts").document(post_id)
    snapshot = post_ref.get()
    if not snapshot.exists:
        raise HTTPException(status_code=404, detail="Post not found")

    data = snapshot.to_dict() or {}
    liked_by = {str(x) for x in (data.get("likedBy") or []) if str(x).strip()}
    disliked_by = {str(x) for x in (data.get("dislikedBy") or []) if str(x).strip()}

    if body.type == "like":
        liked_by.add(uid)
        disliked_by.discard(uid)
    else:
        disliked_by.add(uid)
        liked_by.discard(uid)

    likes = len(liked_by)
    dislikes = len(disliked_by)
    current_user_reaction = "liked" if uid in liked_by else "disliked" if uid in disliked_by else None

    post_ref.set(
        {
            "likedBy": sorted(liked_by),
            "dislikedBy": sorted(disliked_by),
            "likes": likes,
            "dislikes": dislikes,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        },
        merge=True,
    )

    return JSONResponse(
        content={
            "ok": True,
            "postId": post_id,
            "currentUserReaction": current_user_reaction,
            "likes": likes,
            "dislikes": dislikes,
        },
        status_code=200,
    )


@router.delete("/posts/{post_id}/reaction")
def clear_post_reaction(post_id: str, current_user: dict = Depends(get_current_user)):
    uid = str(current_user.get("uid") or "").strip()
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid user.")

    db = get_db_client()
    post_ref = db.collection("posts").document(post_id)
    snapshot = post_ref.get()
    if not snapshot.exists:
        raise HTTPException(status_code=404, detail="Post not found")

    data = snapshot.to_dict() or {}
    liked_by = {str(x) for x in (data.get("likedBy") or []) if str(x).strip()}
    disliked_by = {str(x) for x in (data.get("dislikedBy") or []) if str(x).strip()}
    liked_by.discard(uid)
    disliked_by.discard(uid)

    likes = len(liked_by)
    dislikes = len(disliked_by)

    post_ref.set(
        {
            "likedBy": sorted(liked_by),
            "dislikedBy": sorted(disliked_by),
            "likes": likes,
            "dislikes": dislikes,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        },
        merge=True,
    )

    return JSONResponse(
        content={
            "ok": True,
            "postId": post_id,
            "currentUserReaction": None,
            "likes": likes,
            "dislikes": dislikes,
        },
        status_code=200,
    )


@router.put("/posts/{post_id}")
def edit_post(post_id: str, payload: dict, current_user: dict = Depends(get_current_user)):
    uid = str(current_user.get("uid") or "").strip()
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid user.")

    db = get_db_client()
    post_ref = db.collection("posts").document(post_id)
    snapshot = post_ref.get()
    if not snapshot.exists:
        raise HTTPException(status_code=404, detail="Post not found")

    existing = snapshot.to_dict() or {}
    owner_uid = str(existing.get("userId") or existing.get("createdBy") or "").strip()
    if owner_uid and owner_uid != uid:
        raise HTTPException(status_code=403, detail="You can only edit your own posts.")

    allowed_fields = {
        "text",
        "rating",
        "title",
        "semesterTaken",
        "attendanceMandatory",
        "wouldRecommend",
        "location",
        "priceRange",
        "bestTimeToGo",
        "courseCode",
        "courseName",
        "professorName",
        "spotName",
        "department",
        "attributes",
    }
    patch = {k: v for k, v in payload.items() if k in allowed_fields}
    patch["updatedAt"] = datetime.now(timezone.utc).isoformat()
    post_ref.set(patch, merge=True)

    refreshed = post_ref.get().to_dict() or {}
    refreshed["id"] = post_id
    return JSONResponse(content={"ok": True, "post": to_json_safe(refreshed)}, status_code=200)


@router.delete("/posts/{post_id}")
def remove_post(post_id: str, current_user: dict = Depends(get_current_user)):
    uid = str(current_user.get("uid") or "").strip()
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid user.")

    db = get_db_client()
    post_ref = db.collection("posts").document(post_id)
    snapshot = post_ref.get()
    if not snapshot.exists:
        raise HTTPException(status_code=404, detail="Post not found")

    existing = snapshot.to_dict() or {}
    owner_uid = str(existing.get("userId") or existing.get("createdBy") or "").strip()
    if owner_uid and owner_uid != uid:
        raise HTTPException(status_code=403, detail="You can only delete your own posts.")

    post_ref.delete()

    if str(existing.get("targetType") or "").strip().lower() == "spot":
        target_id = str(existing.get("targetId") or "").strip()
        if target_id:
            update_spot_rating_summary(db, target_id)

    return JSONResponse(content={"ok": True, "id": post_id}, status_code=200)


@router.post("/posts/{post_id}/report")
def report_post(post_id: str, body: PostReportCreate, current_user: dict = Depends(get_current_user)):
    uid = str(current_user.get("uid") or "").strip()
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid user.")

    reason = body.text.strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Report text cannot be empty.")

    db = get_db_client()
    report_ref = db.collection("reports").document()
    report_ref.set(
        {
            "kind": "post",
            "targetId": post_id,
            "text": reason,
            "reportedBy": uid,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
    )

    return JSONResponse(content={"ok": True, "id": report_ref.id, "message": "Report submitted."}, status_code=201)


@router.post("/spots/{spot_id}/report")
def report_spot(spot_id: str, body: SpotReportCreate, current_user: dict = Depends(get_current_user)):
    uid = str(current_user.get("uid") or "").strip()
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid user.")

    reason = body.text.strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Report text cannot be empty.")

    db = get_db_client()
    report_ref = db.collection("reports").document()
    report_ref.set(
        {
            "kind": "spot",
            "targetId": spot_id,
            "text": reason,
            "reportedBy": uid,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
    )

    return JSONResponse(content={"ok": True, "id": report_ref.id, "message": "Report submitted."}, status_code=201)


@router.post("/favorites")
def add_favorite(body: FavoriteCreate, current_user: dict = Depends(get_current_user)):
    uid = str(current_user.get("uid") or "").strip()
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid user.")

    target_id = body.targetId.strip()
    target_name = body.targetName.strip() or target_id
    if not target_id:
        raise HTTPException(status_code=400, detail="targetId is required.")

    doc_id = _favorite_doc_id(uid, body.targetType, target_id)
    db = get_db_client()
    favorite_ref = db.collection("favorites").document(doc_id)
    favorite_ref.set(
        {
            "userId": uid,
            "targetType": body.targetType,
            "targetId": target_id,
            "targetName": target_name,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        },
        merge=True,
    )

    return JSONResponse(content={"ok": True}, status_code=200)


@router.delete("/favorites")
def remove_favorite(
    targetType: Literal["professor", "course", "spot", "post"] = Query(...),
    targetId: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    uid = str(current_user.get("uid") or "").strip()
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid user.")

    target_id = targetId.strip()
    if not target_id:
        raise HTTPException(status_code=400, detail="targetId is required.")

    doc_id = _favorite_doc_id(uid, targetType, target_id)
    db = get_db_client()
    db.collection("favorites").document(doc_id).delete()
    return JSONResponse(content={"ok": True}, status_code=200)


@router.get("/favorites/me")
def get_my_favorites(current_user: dict = Depends(get_current_user)):
    uid = str(current_user.get("uid") or "").strip()
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid user.")

    db = get_db_client()
    docs = db.collection("favorites").where("userId", "==", uid).stream()

    items: list[dict] = []
    posts: list[dict] = []
    professors: list[dict] = []
    courses: list[dict] = []
    spots: list[dict] = []

    for doc in docs:
        data = to_json_safe(doc.to_dict() or {})
        item = {"id": doc.id, **data}
        items.append(item)

        target_type = str(item.get("targetType") or "").strip().lower()
        if target_type == "professor":
            professors.append(item)
        elif target_type == "course":
            courses.append(item)
        elif target_type == "spot":
            spots.append(item)
        elif target_type == "post":
            post_id = str(item.get("targetId") or "").strip()
            if post_id:
                post_snap = db.collection("posts").document(post_id).get()
                if post_snap.exists:
                    posts.append({"id": post_snap.id, **to_json_safe(post_snap.to_dict() or {})})

    return JSONResponse(
        content={
            "items": items,
            "professors": professors,
            "courses": courses,
            "spots": spots,
            "posts": posts,
        },
        status_code=200,
    )