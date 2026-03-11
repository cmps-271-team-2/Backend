from datetime import date, datetime, timezone
from collections import defaultdict, deque
import os
import random

import firebase_admin
from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from firebase_admin import credentials, firestore

from app.jobs.index_posts import upload_post
from app.services.moderation_service import get_moderation_service
from app.services.semantic_service import get_semantic_service

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
    firebase_admin.initialize_app(cred)

db = firestore.client()

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

    # 3) Build weighted pattern: e.g. profile, profile, cafeteria, post...
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

        # Try preferred type first
        if ok(preferred):
            return preferred

        # Otherwise try alternatives (random order so fallback isn't biased)
        types = list(weights.keys())
        rng.shuffle(types)
        for t in types:
            if ok(t):
                return t

        # If everything violates streak, relax streak rule as last resort
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

        # Update streak
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
        "message": "Flask is connected to Firestore"
    }


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
    """
    Returns a mixed randomized feed from your collections.
    Query params:
      - limit (default 20)
      - user_id (optional; used to seed randomness so it stays stable per day)
      - include_posts (0/1, default 1)
    """
    limit = int(request.query_params.get("limit", 20))
    user_id = request.query_params.get("user_id", "guest")
    include_posts = request.query_params.get("include_posts", "1") == "1"

    # Stable "random" per user per day (so refresh doesn't reshuffle constantly)
    seed = hash(f"{user_id}-{date.today().isoformat()}")

    # Fetch candidates (limit to keep it fast)
    prof_docs = db.collection("profiles").limit(100).stream()
    cafe_docs = db.collection("cafeterias").limit(100).stream()

    profiles = [{"id": d.id, "type": "profile", **(d.to_dict() or {})} for d in prof_docs]
    cafeterias = [{"id": d.id, "type": "cafeteria", **(d.to_dict() or {})} for d in cafe_docs]

    items = profiles + cafeterias

    if include_posts:
        post_docs = db.collection("posts").limit(100).stream()
        posts = [{"id": d.id, "type": "post", **(d.to_dict() or {})} for d in post_docs]
        items += posts

    # Weights: controls how frequently each type appears
    # Tweak these to your liking.
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
# Create endpoints (for later users adding data)
# -------------------------------

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
    pending_moderation = {
        "status": "pending",
        "allowed": False,
        "violations": [],
        "explanation": "Moderation pending.",
        "model": None,
        "checkedAt": None,
        "forcedByAdmin": False,
    }
    doc_ref.set({**data, "indexed": False, "moderation": pending_moderation})

    try:
        decision = get_moderation_service().moderate_post(data)
    except Exception:
        return JSONResponse(
            content={"error": "Post moderation is currently unavailable.", "id": doc_ref.id},
            status_code=503,
        )

    moderation_payload = {
        "status": decision.status,
        "allowed": decision.allowed,
        "violations": decision.violations,
        "explanation": decision.explanation,
        "model": decision.model,
        "checkedAt": datetime.now(timezone.utc).isoformat(),
        "forcedByAdmin": False,
    }

    doc_ref.set({"moderation": moderation_payload}, merge=True)

    index_result = {
        "postId": doc_ref.id,
        "indexed": False,
        "indexing_version": None,
    }

    if decision.allowed:
        try:
            index_result = upload_post(doc_ref.id)
        except Exception:
            doc_ref.set(
                {
                    "indexed": False,
                    "moderation": {
                        **moderation_payload,
                        "status": "review",
                        "allowed": False,
                        "explanation": "Automatic indexing failed and post needs manual review.",
                    },
                },
                merge=True,
            )
            return JSONResponse(
                content={
                    "id": doc_ref.id,
                    "indexing": index_result,
                    "moderation": {
                        **moderation_payload,
                        "status": "review",
                        "allowed": False,
                        "explanation": "Automatic indexing failed and post needs manual review.",
                    },
                    "message": "Post created but needs admin review before it can appear in semantic search.",
                },
                status_code=202,
            )

    if not decision.allowed:
        return JSONResponse(
            content={
                "id": doc_ref.id,
                "indexing": index_result,
                "moderation": moderation_payload,
                "message": "Post created but is not accepted yet. An admin can review it from the dashboard.",
            },
            status_code=201,
        )

    return JSONResponse(
        content={
            "id": doc_ref.id,
            "indexing": index_result,
            "moderation": moderation_payload,
            "message": "Post created and indexed successfully.",
        },
        status_code=201,
    )


app = FastAPI()
app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.feed.routes:app", host="127.0.0.1", port=8000, reload=True)

# Call GET /feed?limit=20&user_id=XYZ
# It returns a mixed list.
# Each item contains a type field.
# Render based on type.