<<<<<<<< HEAD:main.py
from fastapi import FastAPI, Query, HTTPException
========
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
import os
from dotenv import load_dotenv
import firebase_admin
>>>>>>>> dev:app/feed/routes.py
from firebase_admin import credentials, firestore
import firebase_admin

from pydantic import BaseModel
from typing import Optional, Literal
from collections import defaultdict, deque
import random
from datetime import date

<<<<<<<< HEAD:main.py
app = FastAPI()

# -------------------------------
# Firebase Init
# -------------------------------
if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")
========
# Load environment variables
load_dotenv()

router = APIRouter()

# Initialize Firebase Admin with environment variables
if not firebase_admin._apps:
    private_key = os.environ["FIREBASE_PRIVATE_KEY"].replace("\\n", "\n")
    
    service_account_info = {
        "type": os.environ["FIREBASE_TYPE"],
        "project_id": os.environ["FIREBASE_PROJECT_ID"],
        "private_key_id": os.environ["FIREBASE_PRIVATE_KEY_ID"],
        "private_key": private_key,
        "client_email": os.environ["FIREBASE_CLIENT_EMAIL"],
        "client_id": os.environ["FIREBASE_CLIENT_ID"],
        "auth_uri": os.environ["FIREBASE_AUTH_URI"],
        "token_uri": os.environ["FIREBASE_TOKEN_URI"],
        "auth_provider_x509_cert_url": os.environ["FIREBASE_AUTH_PROVIDER_X509_CERT_URL"],
        "client_x509_cert_url": os.environ["FIREBASE_CLIENT_X509_CERT_URL"],
        "universe_domain": os.environ["FIREBASE_UNIVERSE_DOMAIN"],
    }
    
    cred = credentials.Certificate(service_account_info)
>>>>>>>> dev:app/feed/routes.py
    firebase_admin.initialize_app(cred)

db = firestore.client()


# -------------------------------
# Pydantic Models
# -------------------------------
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
# Sorting Helper
# -------------------------------
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

    direction = firestore.Query.ASCENDING if order == "asc" else firestore.Query.DESCENDING
    docs = db.collection(collection_name).order_by(sort_by, direction=direction).stream()

    items = []
    for doc in docs:
        items.append({
            "id": doc.id,
            **(doc.to_dict() or {})
        })

    return items


# -------------------------------
# Routes
# -------------------------------
<<<<<<<< HEAD:main.py
@app.get("/")
========

@router.get("/")
>>>>>>>> dev:app/feed/routes.py
def home():
    return {
        "status": "ok",
        "message": "FastAPI is connected to Firestore"
    }


<<<<<<<< HEAD:main.py
@app.get("/profiles")
def get_profiles(
    sort_by: str = Query("name"),
    order: Literal["asc", "desc"] = Query("asc")
):
    return fetch_sorted_collection(
        collection_name="profiles",
        allowed_sort_fields=["name", "type"],
        sort_by=sort_by,
        order=order
    )


@app.get("/cafeterias")
def get_cafeterias(
    sort_by: str = Query("name"),
    order: Literal["asc", "desc"] = Query("asc")
):
    return fetch_sorted_collection(
        collection_name="cafeterias",
        allowed_sort_fields=["name"],
        sort_by=sort_by,
        order=order
    )


@app.get("/posts")
def get_posts(
    sort_by: str = Query("createdAt"),
    order: Literal["asc", "desc"] = Query("desc")
):
    return fetch_sorted_collection(
        collection_name="posts",
        allowed_sort_fields=["rating", "createdAt", "targetType"],
        sort_by=sort_by,
        order=order
    )


@app.get("/courses")
def get_courses(
    sort_by: str = Query("code"),
    order: Literal["asc", "desc"] = Query("asc")
):
    return fetch_sorted_collection(
        collection_name="courses",
        allowed_sort_fields=["code", "title", "department", "number", "ratingAvg", "ratingCount"],
        sort_by=sort_by,
        order=order
    )


@app.get("/feed")
def get_feed(
    limit: int = Query(20),
    user_id: str = Query("guest"),
    include_posts: bool = Query(True),
    sort_by: Optional[str] = Query(None),
    order: Literal["asc", "desc"] = Query("desc")
):
========
@router.get("/profiles")
def get_profiles():
    docs = db.collection("profiles").stream()
    profiles = []

    for doc in docs:
        profiles.append({
            "id": doc.id,
            **doc.to_dict()
        })

    return JSONResponse(content=profiles, status_code=200)


@router.get("/cafeterias")
def get_cafeterias():
    docs = db.collection("cafeterias").stream()
    cafeterias = []

    for doc in docs:
        cafeterias.append({
            "id": doc.id,
            **doc.to_dict()
        })

    return JSONResponse(content=cafeterias, status_code=200)


@router.get("/posts")
def get_posts():
    docs = db.collection("posts").stream()
    posts = []

    for doc in docs:
        posts.append({
            "id": doc.id,
            **doc.to_dict()
        })

    return JSONResponse(content=posts, status_code=200)


# -------------------------------
# NEW: Mixed Random Feed Endpoint
# -------------------------------
@router.get("/feed")
def get_feed(request: Request):
>>>>>>>> dev:app/feed/routes.py
    """
    Returns a mixed randomized feed from your collections.
    Query params:
      - limit
      - user_id
      - include_posts
      - sort_by (optional: rating, name)
      - order (asc/desc)
    """
<<<<<<<< HEAD:main.py
========
    limit = int(request.query_params.get("limit", 20))
    user_id = request.query_params.get("user_id", "guest")
    include_posts = request.query_params.get("include_posts", "1") == "1"

    # Stable "random" per user per day (so refresh doesn't reshuffle constantly)
>>>>>>>> dev:app/feed/routes.py
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

<<<<<<<< HEAD:main.py
    reverse = (order == "desc")

    if sort_by == "rating":
        mixed.sort(key=lambda x: x.get("rating", 0), reverse=reverse)
    elif sort_by == "name":
        mixed.sort(key=lambda x: str(x.get("name", "")).lower(), reverse=reverse)

    return mixed
========
    return JSONResponse(content=mixed, status_code=200)
>>>>>>>> dev:app/feed/routes.py


# -------------------------------
# Create endpoints
# -------------------------------
<<<<<<<< HEAD:main.py
@app.post("/profiles")
def create_profile(data: ProfileCreate):
    doc_ref = db.collection("profiles").document()
    doc_ref.set(data.dict())
    return {"id": doc_ref.id}


@app.post("/cafeterias")
def create_cafeteria(data: CafeteriaCreate):
    doc_ref = db.collection("cafeterias").document()
    doc_ref.set(data.dict())
    return {"id": doc_ref.id}


@app.post("/posts")
def create_post(data: PostCreate):
========

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

>>>>>>>> dev:app/feed/routes.py
    doc_ref = db.collection("posts").document()

<<<<<<<< HEAD:main.py
    doc_ref.set({
        "rating": data.rating,
        "text": data.text,
        "targetId": data.targetId,
        "targetType": data.targetType,
        "createdAt": firestore.SERVER_TIMESTAMP
    })

    return {"id": doc_ref.id}
========
    return JSONResponse(content={"id": doc_ref.id}, status_code=201)


app = FastAPI()
app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.feed.routes:app", host="127.0.0.1", port=8000, reload=True)

# Call GET /feed?limit=20&user_id=XYZ
# It returns a mixed list.
# Each item contains a type field.
# Render based on type.
>>>>>>>> dev:app/feed/routes.py
