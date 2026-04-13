import firebase_admin
from firebase_admin import credentials, firestore
import os


def init_firebase():
    if not firebase_admin._apps:
        cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

        # Prefer explicit service-account file path when provided.
        if cred_path:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
            return

        # Fallback to inline Firebase service-account fields from .env.
        private_key = os.getenv("FIREBASE_PRIVATE_KEY")
        if private_key:
            private_key = private_key.replace("\\n", "\n")

            required_fields = {
                "FIREBASE_TYPE": os.getenv("FIREBASE_TYPE"),
                "FIREBASE_PROJECT_ID": os.getenv("FIREBASE_PROJECT_ID"),
                "FIREBASE_PRIVATE_KEY_ID": os.getenv("FIREBASE_PRIVATE_KEY_ID"),
                "FIREBASE_CLIENT_EMAIL": os.getenv("FIREBASE_CLIENT_EMAIL"),
                "FIREBASE_CLIENT_ID": os.getenv("FIREBASE_CLIENT_ID"),
                "FIREBASE_AUTH_URI": os.getenv("FIREBASE_AUTH_URI"),
                "FIREBASE_TOKEN_URI": os.getenv("FIREBASE_TOKEN_URI"),
                "FIREBASE_AUTH_PROVIDER_X509_CERT_URL": os.getenv("FIREBASE_AUTH_PROVIDER_X509_CERT_URL"),
                "FIREBASE_CLIENT_X509_CERT_URL": os.getenv("FIREBASE_CLIENT_X509_CERT_URL"),
                "FIREBASE_UNIVERSE_DOMAIN": os.getenv("FIREBASE_UNIVERSE_DOMAIN"),
            }

            missing = [name for name, value in required_fields.items() if not value]
            if missing:
                raise Exception(
                    "Missing Firebase env vars: " + ", ".join(missing)
                )

            service_account_info = {
                "type": required_fields["FIREBASE_TYPE"],
                "project_id": required_fields["FIREBASE_PROJECT_ID"],
                "private_key_id": required_fields["FIREBASE_PRIVATE_KEY_ID"],
                "private_key": private_key,
                "client_email": required_fields["FIREBASE_CLIENT_EMAIL"],
                "client_id": required_fields["FIREBASE_CLIENT_ID"],
                "auth_uri": required_fields["FIREBASE_AUTH_URI"],
                "token_uri": required_fields["FIREBASE_TOKEN_URI"],
                "auth_provider_x509_cert_url": required_fields["FIREBASE_AUTH_PROVIDER_X509_CERT_URL"],
                "client_x509_cert_url": required_fields["FIREBASE_CLIENT_X509_CERT_URL"],
                "universe_domain": required_fields["FIREBASE_UNIVERSE_DOMAIN"],
            }

            cred = credentials.Certificate(service_account_info)
            firebase_admin.initialize_app(cred)
            return

        # Last fallback: use Application Default Credentials if available.
        firebase_admin.initialize_app()


def get_db():
    init_firebase()
    return firestore.client()