from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from typing import TypeVar

from fastapi import APIRouter, Depends

from app.admin.dtos import (
    AnalyticsDTO,
    ListPostsQueryDTO,
    ListProfilesQueryDTO,
    PagedResponseDTO,
    PostDTO,
    ProfileDTO,
)

router = APIRouter(tags=["admin"])


_rng = random.Random(1337)
_cache: dict[str, object] = {}


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


TPick = TypeVar("TPick")


def _pick(values: list[TPick], weights: list[int] | None = None) -> TPick:
    if weights is None:
        return _rng.choice(values)
    return _rng.choices(values, weights=weights, k=1)[0]


def _get_mock_profiles() -> list[ProfileDTO]:
    cached = _cache.get("profiles")
    if isinstance(cached, list):
        return cached  # type: ignore[return-value]

    now = datetime.now(timezone.utc)
    first_names = [
        "Lina",
        "Omar",
        "Nour",
        "Jad",
        "Maya",
        "Rami",
        "Sara",
        "Karim",
        "Lea",
        "Hadi",
        "Tala",
        "Yara",
        "Ziad",
        "Aya",
    ]
    last_names = [
        "Haddad",
        "Khoury",
        "Salameh",
        "Nassar",
        "Karam",
        "Mansour",
        "Hobeika",
        "Farah",
        "Sabbagh",
        "Hanna",
        "Saad",
        "Aoun",
        "Sader",
        "Lahad"
    ]

    roles = ["student", "staff", "faculty", "admin"]
    statuses = ["active", "pending", "suspended"]

    profiles: list[ProfileDTO] = []
    for i in range(1, 151):
        fn = _pick(first_names)
        ln = _pick(last_names)
        role = _pick(roles, weights=[80, 12, 6, 2])
        status = _pick(statuses, weights=[86, 10, 4])

        created_at = now - timedelta(days=_rng.randint(0, 240), hours=_rng.randint(0, 23))
        last_active_at = now - timedelta(days=_rng.randint(0, 20), hours=_rng.randint(0, 23))

        display_name = f"{fn} {ln}"
        email_local = f"{fn}.{ln}.{i}".lower()

        profiles.append(
            ProfileDTO(
                id=f"u_{i:04d}",
                displayName=display_name,
                email=f"{email_local}@mail.aub.edu",
                role=role,
                status=status,
                createdAt=_iso(created_at),
                lastActiveAt=_iso(last_active_at),
            )
        )

    _cache["profiles"] = profiles
    return profiles


def _get_mock_posts() -> list[PostDTO]:
    cached = _cache.get("posts")
    if isinstance(cached, list):
        return cached  # type: ignore[return-value]

    now = datetime.now(timezone.utc)
    profiles = _get_mock_profiles()

    titles = [
        "Looking for CS study group",
        "Best coffee spots near campus",
        "Selling calculus textbook",
        "Internship tips for summer",
        "Roommate needed (Hamra)",
        "Lost ID card",
        "Event: AI club meetup",
        "PSA: midterm schedule",
        "Gym buddy search",
        "Project partner needed",
    ]
    tags_pool = ["campus", "events", "housing", "books", "food", "clubs", "jobs", "help", "lost"]

    statuses = ["published", "draft", "flagged"]

    posts: list[PostDTO] = []
    for i in range(1, 281):
        author = _pick(profiles)
        status = _pick(statuses, weights=[78, 15, 7])
        created_at = now - timedelta(days=_rng.randint(0, 60), hours=_rng.randint(0, 23))
        tag_count = _rng.randint(1, 3)
        tags = sorted({_pick(tags_pool) for _ in range(tag_count)})

        like_count = int(abs(_rng.gauss(18, 20)))
        report_count = 0
        if status == "flagged":
            report_count = _rng.randint(1, 12)

        posts.append(
            PostDTO(
                id=f"p_{i:05d}",
                title=f"{_pick(titles)} #{_rng.randint(1, 999)}",
                authorId=author.id,
                authorName=author.displayName,
                status=status,
                tags=tags,
                createdAt=_iso(created_at),
                likeCount=like_count,
                reportCount=report_count,
            )
        )

    _cache["posts"] = posts
    return posts


@router.get("/mock/profiles", response_model=PagedResponseDTO[ProfileDTO])
def list_mock_profiles(q: ListProfilesQueryDTO = Depends()):
    profiles = _get_mock_profiles()

    filtered: list[ProfileDTO] = []
    search_norm = (q.search or "").strip().lower()

    for p in profiles:
        if q.role != "all" and p.role != q.role:
            continue
        if q.status != "all" and p.status != q.status:
            continue
        if search_norm:
            hay = f"{p.id} {p.displayName} {p.email}".lower()
            if search_norm not in hay:
                continue
        filtered.append(p)

    total = len(filtered)
    items = filtered[q.offset : q.offset + q.limit]
    next_offset = q.offset + q.limit if q.offset + q.limit < total else None

    return {
        "total": total,
        "items": items,
        "offset": q.offset,
        "limit": q.limit,
        "nextOffset": next_offset,
    }


@router.get("/mock/posts", response_model=PagedResponseDTO[PostDTO])
def list_mock_posts(q: ListPostsQueryDTO = Depends()):
    posts = _get_mock_posts()

    filtered: list[PostDTO] = []
    search_norm = (q.search or "").strip().lower()
    tag_norm = q.tag.strip().lower() if isinstance(q.tag, str) else "all"

    for p in posts:
        if q.status != "all" and p.status != q.status:
            continue
        if tag_norm != "all" and tag_norm not in [t.lower() for t in p.tags]:
            continue
        if search_norm:
            hay = f"{p.id} {p.title} {p.authorName} {' '.join(p.tags)}".lower()
            if search_norm not in hay:
                continue
        filtered.append(p)

    total = len(filtered)
    items = filtered[q.offset : q.offset + q.limit]
    next_offset = q.offset + q.limit if q.offset + q.limit < total else None

    return {
        "total": total,
        "items": items,
        "offset": q.offset,
        "limit": q.limit,
        "nextOffset": next_offset,
    }


@router.get("/mock/analytics", response_model=AnalyticsDTO)
def get_mock_analytics():
    now = datetime.now(timezone.utc)

    profiles = _get_mock_profiles()
    posts = _get_mock_posts()

    active_profiles = sum(1 for p in profiles if p.status == "active")
    pending_profiles = sum(1 for p in profiles if p.status == "pending")
    suspended_profiles = sum(1 for p in profiles if p.status == "suspended")

    flagged_posts = sum(1 for p in posts if p.status == "flagged")
    drafts = sum(1 for p in posts if p.status == "draft")

    # simple 7-day series
    series: list[dict[str, int | str]] = []
    for days_ago in range(6, -1, -1):
        day = (now - timedelta(days=days_ago)).date().isoformat()
        # deterministic-ish but varied
        signups = 6 + _rng.randint(0, 18)
        posts_created = 10 + _rng.randint(0, 25)
        reports = _rng.randint(0, 6)
        series.append(
            {
                "day": day,
                "signups": signups,
                "posts": posts_created,
                "reports": reports,
            }
        )

    totals = {
        "profilesTotal": len(profiles),
        "profilesActive": active_profiles,
        "profilesPending": pending_profiles,
        "profilesSuspended": suspended_profiles,
        "postsTotal": len(posts),
        "postsFlagged": flagged_posts,
        "postsDraft": drafts,
    }

    return {
        "generatedAt": _iso(now),
        "totals": totals,
        "series7d": series,
    }
