from __future__ import annotations

from typing import Generic, Literal, TypeVar

from fastapi import Query
from pydantic import BaseModel


TargetTypeDTO = Literal["profile", "cafeteria", "other"]

AdminStatusDTO = Literal["active", "banned"]
AdminModerationStatusDTO = Literal["pending", "approved", "rejected", "review"]

JobStatusDTO = Literal["queued", "running", "succeeded", "failed", "canceled"]
JobKindDTO = Literal["ai", "etl", "indexing", "cron", "other"]


class AdminProfileDTO(BaseModel):
    """A rateable profile/target from Firestore `profiles` collection."""

    id: str
    name: str
    location: str | None = None
    ratingAvg: float = 0
    ratingCount: int = 0
    reports: int = 0
    status: AdminStatusDTO = "active"
    createdAt: str


class AdminPostDTO(BaseModel):
    """A rating post from Firestore `posts` collection."""

    id: str
    targetId: str
    targetType: str
    text: str
    rating: int = 0
    reports: int = 0
    moderationStatus: AdminModerationStatusDTO = "pending"
    moderationAllowed: bool = False
    moderationExplanation: str | None = None
    moderationViolations: list[str] = []
    forcedByAdmin: bool = False
    indexed: bool = False
    indexingVersion: int | None = None
    createdAt: str


class AdminUserDTO(BaseModel):
    """An auth user profile from Firestore `users` collection."""

    id: str
    email: str
    isVerified: bool = False
    status: AdminStatusDTO = "active"
    createdAt: str


class AdminJobDTO(BaseModel):
    """A compute job for admin observability (mock for now)."""

    id: str
    name: str
    kind: JobKindDTO
    status: JobStatusDTO
    progress: int = 0  # 0..100
    createdAt: str
    startedAt: str | None = None
    updatedAt: str
    etaSeconds: int | None = None


class SeriesPointDTO(BaseModel):
    day: str
    users: int
    posts: int


class AnalyticsDTO(BaseModel):
    generatedAt: str
    totals: dict[str, int]
    series7d: list[SeriesPointDTO]


TItem = TypeVar("TItem")


class PagedResponseDTO(BaseModel, Generic[TItem]):
    total: int
    items: list[TItem]
    offset: int
    limit: int
    nextOffset: int | None = None


class ListProfilesQueryDTO(BaseModel):
    search: str | None = Query(default=None, description="Searches name/location/id")
    location: str | Literal["all"] = Query(default="all")
    status: AdminStatusDTO | Literal["all"] = Query(default="all")
    minReports: int | None = Query(default=None, ge=0)
    maxReports: int | None = Query(default=None, ge=0)
    offset: int = Query(default=0, ge=0)
    limit: int = Query(default=100, ge=1, le=500)


class ListPostsQueryDTO(BaseModel):
    search: str | None = Query(default=None, description="Searches text/targetType/targetId/id")
    targetType: str | Literal["all"] = Query(default="all")
    minRating: int | None = Query(default=None, ge=0, le=5)
    maxRating: int | None = Query(default=None, ge=0, le=5)
    minReports: int | None = Query(default=None, ge=0)
    maxReports: int | None = Query(default=None, ge=0)
    offset: int = Query(default=0, ge=0)
    limit: int = Query(default=100, ge=1, le=500)


class ListUsersQueryDTO(BaseModel):
    search: str | None = Query(default=None, description="Searches email/id")
    verified: bool | Literal["all"] = Query(default="all")
    status: AdminStatusDTO | Literal["all"] = Query(default="all")
    offset: int = Query(default=0, ge=0)
    limit: int = Query(default=100, ge=1, le=500)


class ListJobsQueryDTO(BaseModel):
    search: str | None = Query(default=None, description="Searches name/kind/status/id")
    status: JobStatusDTO | Literal["all"] = Query(default="all")
    kind: JobKindDTO | Literal["all"] = Query(default="all")
    offset: int = Query(default=0, ge=0)
    limit: int = Query(default=100, ge=1, le=500)


class DeleteResultDTO(BaseModel):
    ok: bool
    id: str


class SetBannedBodyDTO(BaseModel):
    banned: bool


class SetBannedResultDTO(BaseModel):
    ok: bool
    id: str
    banned: bool
    status: AdminStatusDTO


class SetPostModerationBodyDTO(BaseModel):
    accepted: bool


class SetPostModerationResultDTO(BaseModel):
    ok: bool
    id: str
    moderationStatus: AdminModerationStatusDTO
    moderationAllowed: bool
    indexed: bool
