import secrets
import os
import logging
from typing import Optional
import hashlib
import hmac

logger = logging.getLogger(__name__)


def generate_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


def get_admin_hash() -> Optional[str]:
    """Return the admin password hash from env or None."""
    return os.environ.get("ADMIN_PASSWORD_HASH")


def verify_admin_password(plain_password: str) -> tuple[bool, str]:
    """Verify password against ADMIN_PASSWORD_HASH.

    Returns (ok, reason) where reason is 'ok', 'not_configured', or 'invalid'.
    """
    stored = get_admin_hash()
    if not stored:
        logger.error("[AdminAuth] ADMIN_PASSWORD_HASH is not set in environment — returning 500")
        return False, "not_configured"

    # Support PBKDF2-stored format: pbkdf2_sha256:iterations:salt_hex:hash_hex
    if stored.startswith("pbkdf2_sha256:"):
        try:
            parts = stored.split(":", 3)  # ["pbkdf2_sha256", iterations, salt_hex, hash_hex]
            iter_s, salt_hex, hash_hex = parts[1], parts[2], parts[3]
            iterations = int(iter_s)
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(hash_hex)
            derived = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, iterations)
            computed_hash = f"pbkdf2_sha256:{iter_s}:{salt_hex}:{derived.hex()}"
            match = hmac.compare_digest(derived, expected)
            logger.info("[AdminAuth] stored hash : %s", stored)
            logger.info("[AdminAuth] computed hash: %s", computed_hash)
            logger.info("[AdminAuth] match: %s", match)
            return match, "ok" if match else "invalid"
        except Exception as e:
            logger.error("[AdminAuth] PBKDF2 verify error: %s", e)
            return False, "invalid"

    logger.error("[AdminAuth] Unknown hash format — must start with 'pbkdf2_sha256:'. Got: %s", stored[:20])
    return False, "not_configured"
