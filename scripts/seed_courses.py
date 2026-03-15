import os, json, time
from app.core.firebase_admin import init_firebase_admin
from app.core.firestore import get_db

init_firebase_admin()
db = get_db()

print("✅ Starting seed_courses.py ...")

# Must appear in Firestore if you're in the correct project
db.collection("debug_seed").document("ping").set({"ping": True, "ts": time.time()})
print("✅ Wrote debug_seed/ping")

def format_id(code: str) -> str:
    return code.strip().replace(" ", "_").replace("/", "_")

def seed_courses():
    path = os.path.join("app", "data", "aub_gened_courses.json")
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
        doc_id = format_id(c["code"])
        ref = db.collection("courses").document(doc_id)

        batch.set(ref, {
            "code": c["code"],
            "title": c["title"],
            "department": c["dept"],
            "number": c["number"],
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

    # verify at least 1 doc exists
    sample = db.collection("courses").limit(1).get()
    print("🔍 courses sample docs:", len(sample))
    print("✅ Done seeding courses!")

if __name__ == "__main__":
    seed_courses()