import os
import json
import time
import firebase_admin
from firebase_admin import credentials, firestore


def get_db():
    if not firebase_admin._apps:
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred)
    return firestore.client()


db = get_db()

print("✅ Starting seed_courses.py ...")

db.collection("debug_seed").document("ping").set({
    "ping": True,
    "ts": time.time()
})
print("✅ Wrote debug_seed/ping")


def format_id(code: str) -> str:
    return code.strip().replace(" ", "_").replace("/", "_")


def seed_courses():
    path = "courses.json"
    print("📄 Loading:", path)

    if not os.path.exists(path):
        print("❌ File not found:", path)
        return

    with open(path, "r", encoding="utf-8") as f:
        courses = json.load(f)

    print("✅ Loaded courses count:", len(courses))
    print("🔎 First course:", courses[0] if courses else "EMPTY")

    batch = db.batch()
    count = 0
    total = 0

    for c in courses:
        code = c.get("code")
        subject = c.get("subject", "")
        number = c.get("number", "")
        title = c.get("title", "")

        if not code:
            continue

        doc_id = format_id(code)
        ref = db.collection("courses").document(doc_id)

        batch.set(ref, {
            "code": code,
            "title": title,
            "department": subject,
            "number": number,
            "ratingAvg": 0,
            "ratingCount": 0
        }, merge=True)

        count += 1
        total += 1

        if count == 400:
            batch.commit()
            print(f"✅ Committed {total}...")
            batch = db.batch()
            count = 0

    if count > 0:
        batch.commit()
        print(f"✅ Final commit. Total {total}")

    sample = db.collection("courses").limit(1).get()
    print("🔍 courses sample docs:", len(sample))
    print("✅ Done seeding courses!")


if __name__ == "__main__":
    seed_courses()