import firebase_admin
from firebase_admin import credentials, firestore
import subprocess
import sys

def get_db():
    if not firebase_admin._apps:
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred)
    return firestore.client()

db = get_db()

def delete_collection(collection_name: str, batch_size: int = 200):
    while True:
        docs = list(db.collection(collection_name).limit(batch_size).stream())
        if not docs:
            break

        batch = db.batch()
        for doc in docs:
            batch.delete(doc.reference)
        batch.commit()

        print(f"🗑️ Deleted {len(docs)} docs from {collection_name}...")

def main():
    print("🧹 Clearing professors collection...")
    delete_collection("professors")

    print("✅ professors collection cleared")
    print("🚀 Rerunning clean extraction + seeding...")

    result = subprocess.run(
        [sys.executable, "scripts/extract_and_seed_professors_from_pdfs.py"],
        check=False
    )

    if result.returncode == 0:
        print("✅ Done. Professors collection was rebuilt cleanly.")
    else:
        print("❌ Reseed script failed.")

if __name__ == "__main__":
    main()