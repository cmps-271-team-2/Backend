from app.core.firebase import get_db as firebase_get_db


def get_db():
    return firebase_get_db()