from __future__ import annotations

from fastapi import APIRouter, Depends

from app.services.firebase_service import get_firebase_service

from app.admin.dtos import (
    AdminPostDTO,
    AdminProfileDTO,
    AnalyticsDTO,
    ListPostsQueryDTO,
    ListProfilesQueryDTO,
    PagedResponseDTO,
)

router = APIRouter(tags=["admin"])


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
