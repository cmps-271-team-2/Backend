import os
import firebase_admin
from firebase_admin import credentials, auth

def init_firebase_admin() -> None:
    """
    Initialize Firebase Admin SDL once.
    Uses the service account fields from env vars.
    """

    if firebase_admin._apps:
        return

    private_key = os.environ["FIREBASE_PRIVATE_KEY"].replace("\\n", "\n")

    service_account_info = {
        "type": os.environ["FIREBASE_TYPE"],
        "project_id": os.environ["FIREBASE_PROJECT_ID"],
        "private_key_id": os.environ["FIREBASE_PRIVATE_KEY_ID"],
        "private_key": private_key,
        "client_email": os.environ["FIREBASE_CLIENT_EMAIL"],
        "client_id": os.environ["FIREBASE_CLIENT_ID"],
        "auth_uri": os.environ["FIREBASE_AUTH_URI"],
        "token_uri": os.environ["FIREBASE_TOKEN_URI"],
        "auth_provider_x509_cert_url": os.environ[
            "FIREBASE_AUTH_PROVIDER_X509_CERT_URL"
        ],
        "client_x509_cert_url": os.environ["FIREBASE_CLIENT_X509_CERT_URL"],
        "universe_domain": os.environ["FIREBASE_UNIVERSE_DOMAIN"],
    }

    cred = credentials.Certificate(service_account_info)
    firebase_admin.initialize_app(cred)

def get_firebase_auth():
    """
    Returns the Firebase Admin Auth module for creating/disabling users, veryfying tokens, etc.
    """
    return auth