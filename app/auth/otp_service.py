import secrets
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
import os

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12
)

def generate_otp() -> str:
    """
    Returns a 6-digit OTP string like "482193".
    """
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(otp: str) -> str:
    otp = otp.strip()
    return pwd_context.hash(otp)



def verify_otp(otp: str, otp_hash: str) -> bool:
    """
    Check if input otp matches stored bcrypt hash.
    """
    return pwd_context.verify(otp, otp_hash)


def otp_expiry_time() -> datetime:
    """
    Returns UTC datetime when OTP expires (now + OTP_EXP_MINUTES).
    """
    minutes = int(os.environ.get("OTP_EXP_MINUTES", "10"))
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)
