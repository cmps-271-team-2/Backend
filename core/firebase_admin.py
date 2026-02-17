import os
import firebase_admin
from firebase_admin import credentials, auth
from pathlib import Path

_firebase_initialized = False
_firebase_error = None


def init_firebase_admin() -> None:
    """
    Initialize Firebase Admin SDK once.
    Uses the service account JSON path from env var FIREBASE_SERVICE_ACCOUNT_PATH.
    Sets _firebase_initialized flag to track status; _firebase_error for diagnostics.
    
    Handles edge cases:
    - Relative paths (converted to absolute from backend directory)
    - Quoted paths (stripped)
    - Accidental "KEY=VALUE" prefix
    """
    global _firebase_initialized, _firebase_error

    # Already initialized?
    if firebase_admin._apps:
        _firebase_initialized = True
        print("✓ Firebase already initialized.")
        return

    # Read from .env (already loaded by main.py)
    service_account_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "").strip()

    if not service_account_path:
        _firebase_error = "FIREBASE_SERVICE_ACCOUNT_PATH not set in backend/.env"
        print(f"⚠ WARNING: {_firebase_error}")
        print("   Firebase features (OTP, auth) will return 503 Service Unavailable.")
        return

    # Defensive: strip "KEY=VALUE" prefix if accidentally included
    if service_account_path.startswith("FIREBASE_SERVICE_ACCOUNT_PATH="):
        service_account_path = service_account_path.split("=", 1)[1].strip()

    # Strip quotes (handle both single and double)
    service_account_path = service_account_path.strip('"').strip("'")

    # Convert relative path to absolute (relative to backend directory)
    path_obj = Path(service_account_path)
    if not path_obj.is_absolute():
        backend_dir = Path(__file__).resolve().parent.parent  # core/ -> backend/
        path_obj = backend_dir / service_account_path

    path_str = str(path_obj)

    # Validate file exists
    if not path_obj.exists():
        _firebase_error = f"Service account JSON not found at: {path_str}"
        print(f"✗ {_firebase_error}")
        return

    if not path_str.endswith(".json"):
        _firebase_error = f"Service account path must be .json file: {path_str}"
        print(f"✗ {_firebase_error}")
        return

    # Initialize Firebase
    try:
        cred = credentials.Certificate(path_str)
        firebase_admin.initialize_app(cred)
        _firebase_initialized = True
        print(f"✓ Firebase initialized from: {path_str}")
    except Exception as e:
        _firebase_error = str(e)
        print(f"✗ Firebase initialization failed: {_firebase_error}")


def is_firebase_initialized() -> bool:
    """
    Returns True if Firebase app is successfully initialized and ready to use.
    """
    return _firebase_initialized


def get_firebase_error() -> str:
    """
    Returns error message if Firebase failed to initialize; empty string if OK.
    """
    return _firebase_error or ""


def get_firebase_auth():
    """
    Returns the Firebase Admin Auth module for creating/disabling users, verifying tokens, etc.
    """
    return auth