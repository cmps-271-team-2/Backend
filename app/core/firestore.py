from firebase_admin import firestore

def get_db():
    """
    Returns the Firestore client for database operations.
    """
    return firestore.client()