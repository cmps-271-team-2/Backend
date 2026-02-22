from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from app.services.firebase_service import get_firebase_service

from app.admin.dtos import (
    AdminJobDTO,
    AdminPostDTO,
    AdminProfileDTO,
    AnalyticsDTO,
    ListJobsQueryDTO,
    ListPostsQueryDTO,
    ListProfilesQueryDTO,
    PagedResponseDTO,
)

router = APIRouter(tags=["admin"])


_jobs_rng = random.Random(20260222)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _get_mock_jobs() -> list[AdminJobDTO]:
    now = datetime.now(timezone.utc)

    # Small, readable set of ongoing jobs; add a couple finished ones for context.
    base = [
        ("ai", "Embedding refresh"),
        ("indexing", "Search re-index"),
        ("etl", "Nightly warehouse sync"),
        ("cron", "Cleanup temp blobs"),
        ("ai", "Moderation batch"),
    ]

    jobs: list[AdminJobDTO] = []
    for i, (kind, name) in enumerate(base, start=1):
        status = _jobs_rng.choices(
            ["running", "queued", "succeeded", "failed"],
            weights=[60, 25, 12, 3],
            k=1,
        )[0]

        created_at = now - timedelta(minutes=_jobs_rng.randint(2, 240))
        started_at = None
        progress = 0
        eta = None

        if status in ("running", "succeeded", "failed"):
            started_at = created_at + timedelta(minutes=_jobs_rng.randint(0, 8))
        if status == "running":
            progress = _jobs_rng.randint(3, 97)
            eta = _jobs_rng.randint(30, 45 * 60)
        elif status == "queued":
            progress = 0
            eta = _jobs_rng.randint(60, 30 * 60)
        elif status == "succeeded":
            progress = 100
        elif status == "failed":
            progress = _jobs_rng.randint(1, 95)

        updated_at = now - timedelta(seconds=_jobs_rng.randint(0, 180))

        jobs.append(
            AdminJobDTO(
                id=f"job_{i:04d}",
                name=name,
                kind=kind,  # type: ignore[arg-type]
                status=status,  # type: ignore[arg-type]
                progress=progress,
                createdAt=_iso(created_at),
                startedAt=_iso(started_at) if started_at else None,
                updatedAt=_iso(updated_at),
                etaSeconds=eta,
            )
        )

    # Most recent first
    jobs.sort(key=lambda j: j.createdAt, reverse=True)
    return jobs


def _service():
    return get_firebase_service()


@router.get("/profiles", response_model=PagedResponseDTO[AdminProfileDTO])
def list_mock_profiles(q: ListProfilesQueryDTO = Depends()):
    profiles = _service().list_admin_profiles()

    filtered: list[AdminProfileDTO] = []
    search_norm = (q.search or "").strip().lower()
    location_norm = q.location.strip().lower() if isinstance(q.location, str) else "all"

    for p in profiles:
        if location_norm != "all" and (p.location or "").strip().lower() != location_norm:
            continue
        if search_norm:
            hay = f"{p.id} {p.name} {(p.location or '')}".lower()
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


@router.get("/posts", response_model=PagedResponseDTO[AdminPostDTO])
def list_mock_posts(q: ListPostsQueryDTO = Depends()):
    posts = _service().list_admin_posts()

    filtered: list[AdminPostDTO] = []
    search_norm = (q.search or "").strip().lower()
    type_norm = q.targetType.strip().lower() if isinstance(q.targetType, str) else "all"

    for p in posts:
        if type_norm != "all" and (p.targetType or "").strip().lower() != type_norm:
            continue
        if q.minRating is not None and p.rating < q.minRating:
            continue
        if q.maxRating is not None and p.rating > q.maxRating:
            continue
        if search_norm:
            hay = f"{p.id} {p.text} {p.targetType} {p.targetId}".lower()
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


@router.get("/analytics", response_model=AnalyticsDTO)
def get_mock_analytics():
    return _service().admin_analytics()


@router.get("/jobs", response_model=PagedResponseDTO[AdminJobDTO])
def list_jobs(q: ListJobsQueryDTO = Depends()):
    jobs = _get_mock_jobs()

    filtered: list[AdminJobDTO] = []
    search_norm = (q.search or "").strip().lower()

    for j in jobs:
        if q.status != "all" and j.status != q.status:
            continue
        if q.kind != "all" and j.kind != q.kind:
            continue
        if search_norm:
            hay = f"{j.id} {j.name} {j.kind} {j.status}".lower()
            if search_norm not in hay:
                continue
        filtered.append(j)

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
