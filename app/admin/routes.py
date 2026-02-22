from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

router = APIRouter(tags=["admin"])


ProfileRole = Literal["student", "staff", "faculty", "admin"]
ProfileStatus = Literal["active", "suspended", "pending"]
PostStatus = Literal["published", "draft", "flagged"]


class Profile(BaseModel):
    id: str
    displayName: str
    email: str
    role: ProfileRole
    status: ProfileStatus
    createdAt: str
    lastActiveAt: str


class Post(BaseModel):
    id: str
    title: str
    authorId: str
    authorName: str
    status: PostStatus
    tags: list[str] = Field(default_factory=list)
    createdAt: str
    likeCount: int
    reportCount: int


class PagedResponse(BaseModel):
    total: int
    items: list
    offset: int
    limit: int
    nextOffset: int | None = None


class Analytics(BaseModel):
    generatedAt: str
    totals: dict[str, int]
    series7d: list[dict[str, int | str]]


_rng = random.Random(1337)
_cache: dict[str, object] = {}


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _pick[T](values: list[T], weights: list[int] | None = None) -> T:
    if weights is None:
        return _rng.choice(values)
    return _rng.choices(values, weights=weights, k=1)[0]


def _get_mock_profiles() -> list[Profile]:
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
    ]

    roles: list[ProfileRole] = ["student", "staff", "faculty", "admin"]
    statuses: list[ProfileStatus] = ["active", "pending", "suspended"]

    profiles: list[Profile] = []
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
            Profile(
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


def _get_mock_posts() -> list[Post]:
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

    statuses: list[PostStatus] = ["published", "draft", "flagged"]

    posts: list[Post] = []
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
            Post(
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


@router.get("/mock/profiles", response_model=PagedResponse)
def list_mock_profiles(
    search: str | None = Query(default=None, description="Searches displayName/email/id"),
    role: ProfileRole | Literal["all"] = Query(default="all"),
    status: ProfileStatus | Literal["all"] = Query(default="all"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
):
    profiles = _get_mock_profiles()

    filtered: list[Profile] = []
    search_norm = (search or "").strip().lower()

    for p in profiles:
        if role != "all" and p.role != role:
            continue
        if status != "all" and p.status != status:
            continue
        if search_norm:
            hay = f"{p.id} {p.displayName} {p.email}".lower()
            if search_norm not in hay:
                continue
        filtered.append(p)

    total = len(filtered)
    items = filtered[offset : offset + limit]
    next_offset = offset + limit if offset + limit < total else None

    return {
        "total": total,
        "items": items,
        "offset": offset,
        "limit": limit,
        "nextOffset": next_offset,
    }


@router.get("/mock/posts", response_model=PagedResponse)
def list_mock_posts(
    search: str | None = Query(default=None, description="Searches title/author/tags/id"),
    status: PostStatus | Literal["all"] = Query(default="all"),
    tag: str | Literal["all"] = Query(default="all"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
):
    posts = _get_mock_posts()

    filtered: list[Post] = []
    search_norm = (search or "").strip().lower()
    tag_norm = tag.strip().lower() if isinstance(tag, str) else "all"

    for p in posts:
        if status != "all" and p.status != status:
            continue
        if tag_norm != "all" and tag_norm not in [t.lower() for t in p.tags]:
            continue
        if search_norm:
            hay = f"{p.id} {p.title} {p.authorName} {' '.join(p.tags)}".lower()
            if search_norm not in hay:
                continue
        filtered.append(p)

    total = len(filtered)
    items = filtered[offset : offset + limit]
    next_offset = offset + limit if offset + limit < total else None

    return {
        "total": total,
        "items": items,
        "offset": offset,
        "limit": limit,
        "nextOffset": next_offset,
    }


@router.get("/mock/analytics", response_model=Analytics)
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
