from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from celery.result import AsyncResult

from app.jobs.celery_app import celery_app
from app.jobs.index_posts import fetch_relevant_posts
from app.jobs.tasks import process_post_task, update_posts_index_task, upload_post_task


router = APIRouter(tags=["jobs"])


class UploadPostRequest(BaseModel):
    post_id: str


@router.post("/upload_post")
def upload_post_endpoint(payload: UploadPostRequest):
    task = cast(Any, upload_post_task).delay(payload.post_id)
    return {"task_id": task.id, "status": "queued", "post_id": payload.post_id}


@router.get("/fetched_relevant_posts")
def fetched_relevant_posts_endpoint(query: str = Query(min_length=1), limit: int = Query(default=20, ge=1, le=20)):
    return {"posts": fetch_relevant_posts(query_text=query, limit=limit)}


@router.post("/update_posts_index")
def update_posts_index_endpoint():
    task = cast(Any, update_posts_index_task).delay()
    return {"task_id": task.id, "status": "queued"}


@router.post("/process_post")
def process_post_endpoint(payload: UploadPostRequest):
    task = cast(Any, process_post_task).delay(payload.post_id)
    return {"task_id": task.id, "status": "queued", "post_id": payload.post_id}


@router.get("/tasks/{task_id}")
def get_task_status(task_id: str):
    result = AsyncResult(task_id, app=celery_app)
    if result.state == "FAILURE":
        raise HTTPException(status_code=500, detail=str(result.result))

    return {
        "task_id": task_id,
        "status": result.state,
        "result": result.result if result.ready() else None,
    }