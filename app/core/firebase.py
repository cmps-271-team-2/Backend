import firebase_admin
from firebase_admin import credentials, firestore
import os


def init_firebase():
    if not firebase_admin._apps:
        cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

        if not cred_path:
            raise Exception("Missing GOOGLE_APPLICATION_CREDENTIALS in .env")

        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)


def get_db():
    init_firebase()
    return firestore.client()