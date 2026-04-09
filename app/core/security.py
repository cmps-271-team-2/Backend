import secrets
import os
from typing import Optional

try:
    import bcrypt
except Exception:
    bcrypt = None
import hashlib
import hmac
import base64


def generate_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


def get_admin_hash() -> Optional[str]:
    """Return the admin password hash from env or None."""
    return os.environ.get("ADMIN_PASSWORD_HASH")


def verify_admin_password(plain_password: str) -> bool:
    """Verify a provided plain password against ADMIN_PASSWORD_HASH env value.

    Uses bcrypt. Environment must contain `ADMIN_PASSWORD_HASH` produced by
    `bcrypt.hashpw(password, bcrypt.gensalt()).decode()`.
    """
    stored = get_admin_hash()
    if not stored:
        return False

    # If bcrypt is available and the stored hash looks like bcrypt, use it.
    if bcrypt and (stored.startswith("$2a$") or stored.startswith("$2b$") or stored.startswith("$2y$")):
        try:
            return bcrypt.checkpw(plain_password.encode("utf-8"), stored.encode("utf-8"))
        except Exception:
            return False

    # Support a PBKDF2-stored format: pbkdf2_sha256$iterations$salt_hex$hash_hex
    if stored.startswith("pbkdf2_sha256$"):
        try:
            _, iter_s, salt_hex, hash_hex = stored.split("$", 3)[1:5]
            iterations = int(iter_s)
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(hash_hex)
            derived = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, iterations)
            return hmac.compare_digest(derived, expected)
        except Exception:
            return False

    # Unknown format
    return False
