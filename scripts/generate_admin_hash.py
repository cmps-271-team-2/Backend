#!/usr/bin/env python3
"""Generate a bcrypt hash for an admin password.

Usage:
  - Run without args to generate a random password and print the hash.
  - Provide a password as the first arg to hash a specific password.

Do NOT commit the password or hash to source control; copy the hash to your
`ADMIN_PASSWORD_HASH` environment variable or GitHub Actions secret.
"""
import sys
import secrets
import bcrypt


def generate_password(length: int = 12) -> str:
    return secrets.token_urlsafe(length)[:length]


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


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
