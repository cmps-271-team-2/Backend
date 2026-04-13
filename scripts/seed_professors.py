import os
import json
import time
import firebase_admin
from firebase_admin import credentials, firestore
from collections import defaultdict


def get_db():
    if not firebase_admin._apps:
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred)
    return firestore.client()


db = get_db()

print("✅ Starting seed_professors.py ...")

db.collection("debug_seed").document("ping_professors").set({
    "ping": True,
    "ts": time.time()
})
print("✅ Wrote debug_seed/ping_professors")


def professor_doc_id(name: str) -> str:
    return (
        name.strip()
        .lower()
        .replace(" ", "_")
        .replace(".", "")
        .replace("/", "_")
    )


def seed_professors():
    path = "courses.json"
    print("📄 Loading:", path)

    if not os.path.exists(path):
        print("❌ File not found:", path)
        return

    with open(path, "r", encoding="utf-8") as f:
        courses = json.load(f)

    print("✅ Loaded courses count:", len(courses))

    professors_map = defaultdict(lambda: {"name": "", "courses": []})

    for c in courses:
        course_id = c.get("course_id")
        code = c.get("code", "")
        title = c.get("title", "")
        professors = c.get("professors", [])

        for prof in professors:
            if not prof or prof.strip().lower() in {"tba", "staff", "n/a"}:
                continue

            pid = professor_doc_id(prof)
            professors_map[pid]["name"] = prof

            course_entry = {
                "course_id": course_id,
                "code": code,
                "title": title
            }

            existing_ids = {item["course_id"] for item in professors_map[pid]["courses"]}
            if course_id not in existing_ids:
                professors_map[pid]["courses"].append(course_entry)

    print("🔎 Professors found:", len(professors_map))

    batch = db.batch()
    count = 0
    total = 0

    for pid, prof_doc in professors_map.items():
        prof_doc["courses"].sort(key=lambda x: x["code"])
        ref = db.collection("professors").document(pid)

        batch.set(ref, prof_doc, merge=True)

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

    sample = db.collection("professors").limit(1).get()
    print("🔍 professors sample docs:", len(sample))
    print("✅ Done seeding professors!")


if __name__ == "__main__":
    seed_professors()