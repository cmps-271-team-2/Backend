from app.core.firebase import db


def get_db():
    """Return the shared Firestore client."""
    return db