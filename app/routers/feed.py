from collections import defaultdict, deque
from datetime import date, datetime, timezone
import hashlib
import random
from typing import Any, Optional, Literal, cast

from fastapi import APIRouter, Request, Query, HTTPException, Header
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from firebase_admin import firestore
from pydantic import BaseModel

from app.core.firestore import get_db
from app.core.firebase_admin import get_firebase_auth
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


class ReactionRequest(BaseModel):
    type: Literal["like", "dislike", "liked", "disliked"]


class PostUpdateRequest(BaseModel):
    text: Optional[str] = None
    rating: Optional[int] = None
    title: Optional[str] = None
    semesterTaken: Optional[str] = None
    attendanceMandatory: Optional[bool] = None
    wouldRecommend: Optional[bool] = None
    location: Optional[str] = None
    priceRange: Optional[str] = None
    bestTimeToGo: Optional[str] = None
    courseCode: Optional[str] = None
    courseName: Optional[str] = None
    professorName: Optional[str] = None
    spotName: Optional[str] = None
    department: Optional[str] = None
    attributes: Optional[list[str]] = None


class SpotReportRequest(BaseModel):
    text: str


class PostReportRequest(BaseModel):
    text: str


class FavoriteRequest(BaseModel):
    targetType: Literal["professor", "course", "spot", "post"]
    targetId: str
    targetName: Optional[str] = None


def get_db_client():
    return get_db()


def _parse_bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


def _get_current_user_optional(authorization: Optional[str]) -> Optional[dict[str, Any]]:
    token = _parse_bearer_token(authorization)
    if not token:
        return None
    firebase_auth = get_firebase_auth()
    try:
        decoded = firebase_auth.verify_id_token(token)
        return cast(dict[str, Any], decoded)
    except Exception:
        return None


def _get_current_user_required(authorization: Optional[str]) -> dict[str, Any]:
    user = _get_current_user_optional(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return user


def _favorite_doc_id(user_id: str, target_type: str, target_id: str) -> str:
    return hashlib.sha256(f"{user_id}:{target_type}:{target_id}".encode("utf-8")).hexdigest()


def _normalize_target_type_for_favorite(target_type: str) -> str:
    tt = target_type.strip().lower()
    if tt in {"prof", "professor", "profile"}:
        return "professor"
    if tt in {"course"}:
        return "course"
    if tt in {"post"}:
        return "post"
    return "spot"


def _resolve_target_name(db, target_type: str, target_id: str) -> Optional[str]:
    tid = target_id.strip()
    if not tid:
        return None

    if target_type == "professor":
        for collection_name in ["profiles"]:
            snapshot = db.collection(collection_name).document(tid).get()
            if snapshot.exists:
                data = snapshot.to_dict() or {}
                name = str(data.get("name") or "").strip()
                if name:
                    return name
    elif target_type == "course":
        snapshot = db.collection("courses").document(tid).get()
        if snapshot.exists:
            data = snapshot.to_dict() or {}
            label = str(data.get("code") or "").strip() or str(data.get("title") or "").strip()
            if label:
                return label
    else:
        for collection_name in ["spots", "cafeterias"]:
            snapshot = db.collection(collection_name).document(tid).get()
            if snapshot.exists:
                data = snapshot.to_dict() or {}
                name = str(data.get("name") or "").strip()
                if name:
                    return name

    return None


def _normalize_reaction(value: str) -> Literal["like", "dislike"]:
    normalized = value.strip().lower()
    if normalized in {"like", "liked"}:
        return "like"
    if normalized in {"dislike", "disliked"}:
        return "dislike"
    raise HTTPException(status_code=400, detail="Input should be 'like' or 'dislike'")


def _is_post_owned_by_user(post_data: dict[str, Any], uid: str, email: str, display_name: str) -> bool:
    owner_uid = str(post_data.get("userId") or "").strip()
    owner_created_by = str(post_data.get("createdBy") or "").strip()
    owner_email = str(post_data.get("userEmail") or "").strip().lower()
    owner_display_name = str(post_data.get("displayName") or post_data.get("authorName") or "").strip().lower()

    if uid and (owner_uid == uid or owner_created_by == uid):
        return True

    if email:
        lowered = email.strip().lower()
        email_local = lowered.split("@", 1)[0]
        created_by_lower = owner_created_by.strip().lower()
        if (
            owner_email == lowered
            or created_by_lower == lowered
            or (email_local and created_by_lower == email_local)
        ):
            return True

    if display_name:
        lowered_name = display_name.strip().lower()
        if lowered_name and (owner_display_name == lowered_name or owner_created_by.strip().lower() == lowered_name):
            return True

    return False


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
    authorization: Optional[str] = Header(default=None),
):
    posts = fetch_sorted_collection(
        collection_name="posts",
        allowed_sort_fields=["rating", "createdAt", "targetType"],
        sort_by=sort_by,
        order=order,
    )

    user = _get_current_user_optional(authorization)
    if user:
        uid = str(user.get("uid") or "")
        email = str(user.get("email") or "")
        display_name = str(user.get("name") or "")
        favorites_docs = db = get_db_client()
        favorite_stream = db.collection("favorites").where("userId", "==", uid).stream()
        favorite_keys = {
            f"{str((fav.to_dict() or {}).get('targetType') or '').strip().lower()}:{str((fav.to_dict() or {}).get('targetId') or '').strip()}"
            for fav in favorite_stream
        }

        for post in posts:
            liked_by = [str(x) for x in (post.get("likedBy") or [])]
            disliked_by = [str(x) for x in (post.get("dislikedBy") or [])]
            post["likes"] = len(liked_by)
            post["dislikes"] = len(disliked_by)
            if uid in liked_by:
                post["currentUserReaction"] = "liked"
            elif uid in disliked_by:
                post["currentUserReaction"] = "disliked"
            else:
                post["currentUserReaction"] = None
            post["isOwner"] = _is_post_owned_by_user(post, uid, email, display_name)
            
            # Check if post itself is favorited (post-level) OR if the course/professor/spot is favorited (course-level)
            post_id = str(post.get("id") or "")
            post_fav_key = f"post:{post_id}"
            is_post_favorited = post_fav_key in favorite_keys
            
            fav_target_type = _normalize_target_type_for_favorite(str(post.get("targetType") or ""))
            fav_key = f"{fav_target_type}:{str(post.get('targetId') or '').strip()}"
            is_course_favorited = fav_key in favorite_keys
            
            post["isFavorited"] = is_post_favorited or is_course_favorited
    else:
        for post in posts:
            liked_by = [str(x) for x in (post.get("likedBy") or [])]
            disliked_by = [str(x) for x in (post.get("dislikedBy") or [])]
            post["likes"] = len(liked_by)
            post["dislikes"] = len(disliked_by)
            post["currentUserReaction"] = None
            post["isOwner"] = False
            post["isFavorited"] = False

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
    user = _get_current_user_optional(request.headers.get("Authorization"))

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
            "userId": str((user or {}).get("uid") or ""),
            "userEmail": str((user or {}).get("email") or ""),
            "likes": 0,
            "dislikes": 0,
            "likedBy": [],
            "dislikedBy": [],
            "reports": 0,
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


@router.post("/posts/{post_id}/reaction")
def react_to_post(
    post_id: str,
    body: ReactionRequest,
    authorization: Optional[str] = Header(default=None),
):
    user = _get_current_user_required(authorization)
    uid = str(user.get("uid") or "")
    db = get_db_client()

    post_ref = db.collection("posts").document(post_id)
    snapshot = post_ref.get()
    if not snapshot.exists:
        raise HTTPException(status_code=404, detail="Post not found")

    post_data = snapshot.to_dict() or {}
    liked_by = [str(x) for x in (post_data.get("likedBy") or [])]
    disliked_by = [str(x) for x in (post_data.get("dislikedBy") or [])]

    reaction_type = _normalize_reaction(body.type)

    if reaction_type == "like":
        if uid in liked_by:
            liked_by = [x for x in liked_by if x != uid]
            current_reaction: Optional[str] = None
        else:
            liked_by = [x for x in liked_by if x != uid] + [uid]
            disliked_by = [x for x in disliked_by if x != uid]
            current_reaction = "liked"
    else:
        if uid in disliked_by:
            disliked_by = [x for x in disliked_by if x != uid]
            current_reaction = None
        else:
            disliked_by = [x for x in disliked_by if x != uid] + [uid]
            liked_by = [x for x in liked_by if x != uid]
            current_reaction = "disliked"

    post_ref.set(
        {
            "likedBy": liked_by,
            "dislikedBy": disliked_by,
            "likes": len(liked_by),
            "dislikes": len(disliked_by),
        },
        merge=True,
    )

    if current_reaction == "liked":
        target_type = str(post_data.get("targetType") or "")
        target_id = str(post_data.get("targetId") or "")
        text = str(post_data.get("text") or "")
        snippet = f"{target_type} {target_id}: {text}".strip()

        user_ref = db.collection("users").document(uid)
        user_snapshot = user_ref.get()
        existing_prompt = ""
        if user_snapshot.exists:
            existing_prompt = str((user_snapshot.to_dict() or {}).get("recommendationPrompt") or "")
        new_prompt = (existing_prompt + "\n" + snippet).strip()
        if len(new_prompt) > _MAX_RECOMMENDATION_PROMPT_CHARS:
            lines = new_prompt.splitlines()
            while lines and len("\n".join(lines)) > _MAX_RECOMMENDATION_PROMPT_CHARS:
                lines.pop(0)
            new_prompt = "\n".join(lines)
        user_ref.set({"recommendationPrompt": new_prompt}, merge=True)

    return {
        "ok": True,
        "postId": post_id,
        "currentUserReaction": current_reaction,
        "likes": len(liked_by),
        "dislikes": len(disliked_by),
    }


@router.delete("/posts/{post_id}/reaction")
def clear_reaction(
    post_id: str,
    authorization: Optional[str] = Header(default=None),
):
    user = _get_current_user_required(authorization)
    uid = str(user.get("uid") or "")
    db = get_db_client()

    post_ref = db.collection("posts").document(post_id)
    snapshot = post_ref.get()
    if not snapshot.exists:
        raise HTTPException(status_code=404, detail="Post not found")

    post_data = snapshot.to_dict() or {}
    liked_by = [str(x) for x in (post_data.get("likedBy") or []) if str(x) != uid]
    disliked_by = [str(x) for x in (post_data.get("dislikedBy") or []) if str(x) != uid]

    post_ref.set(
        {
            "likedBy": liked_by,
            "dislikedBy": disliked_by,
            "likes": len(liked_by),
            "dislikes": len(disliked_by),
        },
        merge=True,
    )

    return {
        "ok": True,
        "postId": post_id,
        "currentUserReaction": None,
        "likes": len(liked_by),
        "dislikes": len(disliked_by),
    }


@router.put("/posts/{post_id}")
def update_post(
    post_id: str,
    body: PostUpdateRequest,
    authorization: Optional[str] = Header(default=None),
):
    user = _get_current_user_required(authorization)
    uid = str(user.get("uid") or "")
    db = get_db_client()

    post_ref = db.collection("posts").document(post_id)
    snapshot = post_ref.get()
    if not snapshot.exists:
        raise HTTPException(status_code=404, detail="Post not found")
    post_data = snapshot.to_dict() or {}

    email = str(user.get("email") or "")
    display_name = str(user.get("name") or "")
    if not _is_post_owned_by_user(post_data, uid, email, display_name):
        raise HTTPException(status_code=403, detail="Only the rating owner can edit this post.")

    updates = {
        key: value
        for key, value in body.model_dump().items()
        if value is not None
    }
    if not updates:
        raise HTTPException(status_code=400, detail="No update fields provided.")

    if "text" in updates and not str(updates["text"]).strip():
        raise HTTPException(status_code=400, detail="text cannot be empty.")
    if "rating" in updates:
        rating_value = int(updates["rating"])
        if rating_value < 1 or rating_value > 5:
            raise HTTPException(status_code=400, detail="rating must be between 1 and 5.")

    updates["updatedAt"] = datetime.now(timezone.utc).isoformat()
    post_ref.set(updates, merge=True)

    updated_snapshot = post_ref.get()
    updated = _serialize_doc(updated_snapshot)
    return {"ok": True, "post": updated}


@router.delete("/posts/{post_id}")
def delete_post(
    post_id: str,
    authorization: Optional[str] = Header(default=None),
):
    user = _get_current_user_required(authorization)
    uid = str(user.get("uid") or "")
    db = get_db_client()

    post_ref = db.collection("posts").document(post_id)
    snapshot = post_ref.get()
    if not snapshot.exists:
        raise HTTPException(status_code=404, detail="Post not found")
    post_data = snapshot.to_dict() or {}

    email = str(user.get("email") or "")
    display_name = str(user.get("name") or "")
    if not _is_post_owned_by_user(post_data, uid, email, display_name):
        raise HTTPException(status_code=403, detail="Only the rating owner can delete this post.")

    post_ref.delete()
    return {"ok": True, "id": post_id}


@router.get("/posts/mine")
def get_my_posts(
    authorization: Optional[str] = Header(default=None),
):
    user = _get_current_user_required(authorization)
    uid = str(user.get("uid") or "")
    email = str(user.get("email") or "").strip().lower()
    display_name = str(user.get("name") or "")
    db = get_db_client()

    # Legacy compatibility: older posts may not have userId but can still be linked via createdBy or userEmail.
    docs = db.collection("posts").stream()
    posts = []
    for doc in docs:
        post = _serialize_doc(doc)
        if _is_post_owned_by_user(post, uid, email, display_name):
            posts.append(post)
    posts.sort(key=lambda p: str(p.get("createdAt") or ""), reverse=True)
    return posts


@router.post("/spots/{spot_id}/report")
def report_spot(
    spot_id: str,
    body: SpotReportRequest,
    authorization: Optional[str] = Header(default=None),
):
    user = _get_current_user_required(authorization)
    uid = str(user.get("uid") or "")
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Report text cannot be empty.")
    if len(text) > 2000:
        raise HTTPException(status_code=400, detail="Report text is too long.")

    db = get_db_client()

    spot_exists = db.collection("spots").document(spot_id).get().exists
    cafe_exists = db.collection("cafeterias").document(spot_id).get().exists
    if not spot_exists and not cafe_exists:
        raise HTTPException(status_code=404, detail="Spot not found.")

    report_ref = db.collection("spot_reports").document()
    now_iso = datetime.now(timezone.utc).isoformat()
    report_ref.set(
        {
            "spotId": spot_id,
            "userId": uid,
            "text": text,
            "status": "pending",
            "createdAt": now_iso,
            "updatedAt": now_iso,
        }
    )

    # Increment the reports counter on the spot/cafeteria document
    spot_ref = db.collection("spots").document(spot_id)
    if spot_ref.get().exists:
        spot_ref.update({"reports": firestore.firestore.Increment(1)})
    else:
        cafe_ref = db.collection("cafeterias").document(spot_id)
        if cafe_ref.get().exists:
            cafe_ref.update({"reports": firestore.firestore.Increment(1)})

    return {"ok": True, "id": report_ref.id, "message": "Report submitted."}


@router.post("/posts/{post_id}/report")
def report_post(
    post_id: str,
    body: PostReportRequest,
    authorization: Optional[str] = Header(default=None),
):
    user = _get_current_user_required(authorization)
    uid = str(user.get("uid") or "")
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Report text cannot be empty.")
    if len(text) > 2000:
        raise HTTPException(status_code=400, detail="Report text is too long.")

    db = get_db_client()
    post_snapshot = db.collection("posts").document(post_id).get()
    if not post_snapshot.exists:
        raise HTTPException(status_code=404, detail="Post not found.")

    now_iso = datetime.now(timezone.utc).isoformat()
    report_ref = db.collection("post_reports").document()
    report_ref.set(
        {
            "postId": post_id,
            "userId": uid,
            "text": text,
            "status": "pending",
            "createdAt": now_iso,
            "updatedAt": now_iso,
        }
    )

    # Increment the reports counter on the post document so the admin panel sees it
    db.collection("posts").document(post_id).update(
        {"reports": firestore.firestore.Increment(1)}
    )

    return {"ok": True, "id": report_ref.id, "message": "Report submitted."}


@router.post("/favorites")
def add_favorite(
    body: FavoriteRequest,
    authorization: Optional[str] = Header(default=None),
):
    user = _get_current_user_required(authorization)
    uid = str(user.get("uid") or "")
    target_id = body.targetId.strip()
    if not target_id:
        raise HTTPException(status_code=400, detail="targetId is required.")

    normalized_target_type = _normalize_target_type_for_favorite(body.targetType)

    db = get_db_client()
    target_name = (body.targetName or "").strip()
    resolved_name = _resolve_target_name(db, normalized_target_type, target_id)
    final_name = resolved_name or target_name or target_id

    doc_id = _favorite_doc_id(uid, normalized_target_type, target_id)
    ref = db.collection("favorites").document(doc_id)
    ref.set(
        {
            "userId": uid,
            "targetType": normalized_target_type,
            "targetId": target_id,
            "targetName": final_name,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        },
        merge=True,
    )

    return {
        "ok": True,
        "id": doc_id,
        "targetType": normalized_target_type,
        "targetId": target_id,
        "targetName": final_name,
    }


@router.delete("/favorites")
def remove_favorite(
    targetType: Literal["professor", "course", "spot", "post"] = Query(...),
    targetId: str = Query(...),
    authorization: Optional[str] = Header(default=None),
):
    user = _get_current_user_required(authorization)
    uid = str(user.get("uid") or "")
    tid = targetId.strip()
    if not tid:
        raise HTTPException(status_code=400, detail="targetId is required.")

    db = get_db_client()
    normalized_target_type = _normalize_target_type_for_favorite(targetType)
    doc_id = _favorite_doc_id(uid, normalized_target_type, tid)
    db.collection("favorites").document(doc_id).delete()
    return {"ok": True, "id": doc_id}


@router.get("/favorites/me")
def get_my_favorites(
    authorization: Optional[str] = Header(default=None),
):
    user = _get_current_user_required(authorization)
    uid = str(user.get("uid") or "")
    db = get_db_client()

    docs = db.collection("favorites").where("userId", "==", uid).stream()
    items = [_serialize_doc(doc) for doc in docs]
    items.sort(key=lambda x: str(x.get("createdAt") or ""), reverse=True)

    professors = [item for item in items if str(item.get("targetType") or "") == "professor"]
    courses = [item for item in items if str(item.get("targetType") or "") == "course"]
    spots = [item for item in items if str(item.get("targetType") or "") == "spot"]
    
    # Fetch actual post data for post-level favorites
    post_items = [item for item in items if str(item.get("targetType") or "") == "post"]
    posts = []
    for fav in post_items:
        post_id = str(fav.get("targetId") or "")
        if post_id:
            post_doc = db.collection("posts").document(post_id).get()
            if post_doc.exists:
                post_data = _serialize_doc(post_doc)
                # Add favorite metadata
                post_data["_favoriteId"] = fav.get("id")
                posts.append(post_data)

    return {
        "items": items,
        "professors": professors,
        "courses": courses,
        "spots": spots,
        "posts": posts,
    }