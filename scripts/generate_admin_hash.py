#!/usr/bin/env python3
"""Generate a PBKDF2-SHA256 hash for an admin password.

Usage:
  - Run without args to generate a random password and print the hash.
  - Provide a password as the first arg to hash a specific password.

Do NOT commit the password or hash to source control; copy the hash to your
`ADMIN_PASSWORD_HASH` environment variable or GitHub Actions secret.
"""
import sys
import secrets
import hashlib


def generate_password(length: int = 12) -> str:
    return secrets.token_urlsafe(length)[:length]


def hash_password(pw: str) -> str:
    iterations = 200_000
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${derived.hex()}"


def main():
    if len(sys.argv) > 1:
        pw = sys.argv[1]
    else:
        pw = generate_password()

    hashed = hash_password(pw)
    print("PASSWORD:", pw)
    print("HASH:", hashed)


if __name__ == "__main__":
    main()
