from flask import Flask, jsonify, request
import firebase_admin
from firebase_admin import credentials, firestore

from collections import defaultdict, deque
import random
from datetime import date

app = Flask(__name__)
cred = credentials.Certificate("serviceAccountKey.json")
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

@app.get("/")
def home():
    return {
        "status": "ok",
        "message": "Flask is connected to Firestore"
    }


@app.get("/profiles")
def get_profiles():
    docs = db.collection("profiles").stream()
    profiles = []

    for doc in docs:
        profiles.append({
            "id": doc.id,
            **doc.to_dict()
        })

    return jsonify(profiles), 200


@app.get("/cafeterias")
def get_cafeterias():
    docs = db.collection("cafeterias").stream()
    cafeterias = []

    for doc in docs:
        cafeterias.append({
            "id": doc.id,
            **doc.to_dict()
        })

    return jsonify(cafeterias), 200


@app.get("/posts")
def get_posts():
    docs = db.collection("posts").stream()
    posts = []

    for doc in docs:
        posts.append({
            "id": doc.id,
            **doc.to_dict()
        })

    return jsonify(posts), 200


# -------------------------------
# NEW: Mixed Random Feed Endpoint
# -------------------------------
@app.get("/feed")
def get_feed():
    """
    Returns a mixed randomized feed from your collections.
    Query params:
      - limit (default 20)
      - user_id (optional; used to seed randomness so it stays stable per day)
      - include_posts (0/1, default 1)
    """
    limit = int(request.args.get("limit", 20))
    user_id = request.args.get("user_id", "guest")
    include_posts = request.args.get("include_posts", "1") == "1"

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

    return jsonify(mixed), 200


# -------------------------------
# Create endpoints (for later users adding data)
# -------------------------------

@app.post("/profiles")
def create_profile():
    data = request.get_json()

    if not data or "type" not in data or "name" not in data:
        return jsonify({"error": "Missing required fields"}), 400

    doc_ref = db.collection("profiles").document()
    doc_ref.set(data)

    return jsonify({"id": doc_ref.id}), 201


@app.post("/cafeterias")
def create_cafeteria():
    data = request.get_json()

    if not data or "name" not in data:
        return jsonify({"error": "Missing required field: name"}), 400

    doc_ref = db.collection("cafeterias").document()
    doc_ref.set(data)

    return jsonify({"id": doc_ref.id}), 201


@app.post("/posts")
def create_post():
    data = request.get_json()

    required_fields = ["rating", "text", "targetId", "targetType"]

    if not data or not all(field in data for field in required_fields):
        return jsonify({"error": "Missing required fields"}), 400

    doc_ref = db.collection("posts").document()
    doc_ref.set(data)

    return jsonify({"id": doc_ref.id}), 201


if __name__ == "__main__":
    app.run(debug=True)

# Call GET /feed?limit=20&user_id=XYZ
# It returns a mixed list.
# Each item contains a type field.
# Render based on type.