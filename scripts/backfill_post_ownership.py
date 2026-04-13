#!/usr/bin/env python3
"""
Backfill missing post ownership fields in Firestore.

Why this exists:
- Legacy posts may be missing userId, which breaks /posts/mine and owner actions.
- This script attempts to infer ownership from legacy fields like userEmail,
  createdBy, displayName, and authorName.

Usage:
  python scripts/backfill_post_ownership.py --dry-run
  python scripts/backfill_post_ownership.py --apply
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any

from app.core.firestore import get_db


@dataclass
class UserRecord:
    uid: str
    email: str
    email_local: str
    name: str


def _norm(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _build_user_indexes() -> tuple[dict[str, UserRecord], dict[str, UserRecord], dict[str, UserRecord]]:
    db = get_db()
    docs = db.collection("users").stream()

    by_uid: dict[str, UserRecord] = {}
    by_email: dict[str, UserRecord] = {}
    by_name: dict[str, UserRecord] = {}

    for doc in docs:
        data = doc.to_dict() or {}
        uid = _norm(doc.id)
        email = _norm(data.get("email"))
        name = _norm(data.get("name") or data.get("displayName"))
        email_local = email.split("@", 1)[0] if "@" in email else ""

        record = UserRecord(uid=uid, email=email, email_local=email_local, name=name)
        if uid:
            by_uid[uid] = record
        if email:
            by_email[email] = record
        if name and name not in by_name:
            by_name[name] = record

    return by_uid, by_email, by_name


def _resolve_owner_uid(post: dict[str, Any], by_uid: dict[str, UserRecord], by_email: dict[str, UserRecord], by_name: dict[str, UserRecord]) -> str:
    user_id = _norm(post.get("userId"))
    if user_id:
        return user_id if user_id in by_uid else ""

    user_email = _norm(post.get("userEmail"))
    created_by = _norm(post.get("createdBy"))
    display_name = _norm(post.get("displayName") or post.get("authorName"))

    if user_email and user_email in by_email:
        return by_email[user_email].uid

    if created_by:
        if created_by in by_uid:
            return by_uid[created_by].uid
        if created_by in by_email:
            return by_email[created_by].uid
        # Match by email local-part.
        for user in by_uid.values():
            if user.email_local and created_by == user.email_local:
                return user.uid

    if display_name and display_name in by_name:
        return by_name[display_name].uid

    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill missing post ownership fields")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Only print planned updates")
    mode.add_argument("--apply", action="store_true", help="Write updates to Firestore")
    args = parser.parse_args()

    db = get_db()
    by_uid, by_email, by_name = _build_user_indexes()

    posts = list(db.collection("posts").stream())
    total = len(posts)
    missing = 0
    matched = 0
    updated = 0

    for doc in posts:
        data = doc.to_dict() or {}
        if _norm(data.get("userId")):
            continue

        missing += 1
        resolved_uid = _resolve_owner_uid(data, by_uid, by_email, by_name)
        if not resolved_uid:
            continue

        matched += 1
        update_payload = {"userId": resolved_uid}

        if args.dry_run:
            print(f"[DRY-RUN] would update post {doc.id} -> userId={resolved_uid}")
            continue

        db.collection("posts").document(doc.id).set(update_payload, merge=True)
        updated += 1
        print(f"[APPLY] updated post {doc.id} -> userId={resolved_uid}")

    print("\nSummary")
    print(f"total posts: {total}")
    print(f"missing userId: {missing}")
    print(f"matched owner: {matched}")
    print(f"updated: {updated}")


if __name__ == "__main__":
    main()
