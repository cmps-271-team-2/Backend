from __future__ import annotations

from typing import Generic, Literal, TypeVar

from fastapi import Query
from pydantic import BaseModel, Field


ProfileRoleDTO = Literal["student", "staff", "faculty", "admin"]
ProfileStatusDTO = Literal["active", "suspended", "pending"]
PostStatusDTO = Literal["published", "draft", "flagged"]


class ProfileDTO(BaseModel):
    id: str
    displayName: str
    email: str
    role: ProfileRoleDTO
    status: ProfileStatusDTO
    createdAt: str
    lastActiveAt: str


class PostDTO(BaseModel):
    id: str
    title: str
    authorId: str
    authorName: str
    status: PostStatusDTO
    tags: list[str] = Field(default_factory=list)
    createdAt: str
    likeCount: int
    reportCount: int


class SeriesPointDTO(BaseModel):
    day: str
    signups: int
    posts: int
    reports: int


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
    search: str | None = Query(default=None, description="Searches displayName/email/id")
    role: ProfileRoleDTO | Literal["all"] = Query(default="all")
    status: ProfileStatusDTO | Literal["all"] = Query(default="all")
    offset: int = Query(default=0, ge=0)
    limit: int = Query(default=100, ge=1, le=500)


class ListPostsQueryDTO(BaseModel):
    search: str | None = Query(default=None, description="Searches title/author/tags/id")
    status: PostStatusDTO | Literal["all"] = Query(default="all")
    tag: str | Literal["all"] = Query(default="all")
    offset: int = Query(default=0, ge=0)
    limit: int = Query(default=100, ge=1, le=500)
