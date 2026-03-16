from firebase_admin import firestore

from app.core.firebase_admin import init_firebase_admin


def init_firebase():
    init_firebase_admin()


init_firebase()
db = firestore.client()
