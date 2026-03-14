from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.jobs.index_posts import fetch_relevant_posts, update_posts_index, upload_post


router = APIRouter(tags=["jobs"])


class UploadPostRequest(BaseModel):
    post_id: str


@router.post("/upload_post")
def upload_post_endpoint(payload: UploadPostRequest):
    try:
        return upload_post(payload.post_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/fetched_relevant_posts")
def fetched_relevant_posts_endpoint(query: str = Query(min_length=1), limit: int = Query(default=20, ge=1, le=20)):
    return {"posts": fetch_relevant_posts(query_text=query, limit=limit)}


@router.post("/update_posts_index")
def update_posts_index_endpoint():
    return update_posts_index()