from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Set

router = APIRouter()

#mock database 
reviews_db = [
    {
        "id": 1, 
        "rating": 5, 
        "category": "Professor", 
        "text": "Professor John explains complex algorithms very well. The exams are easy but need good preparation", 
        "major": "Computer Science", "year": "Senior",
        "likes": 15, "dislikes": 0, 
        "liked_users": set(), "disliked_users": set(), "saved_users": set()
    },
    {
        "id": 2, 
        "rating": 4, 
        "category": "Cafe", 
        "text": "The food is decent, but the lines are way too long.", 
        "major": "Business", "year": "Sophomore",
        "likes": 8, "dislikes": 0, 
        "liked_users": set(), "disliked_users": set(), "saved_users": set()
    },
]

class ActionRequest(BaseModel):
    review_id: int
    user_id: str
    action: str

@router.get("/reviews")
def get_all_reviews(user_id: str = "myUser123"):
    return [
        {
            "id": r["id"],
            "rating": r["rating"],
            "category": r["category"],
            "text": r["text"],
            "major": r["major"],
            "year": r["year"],
            "likes": r["likes"],
            "dislikes": r["dislikes"],
            "has_liked": user_id in r["liked_users"],
            "has_disliked": user_id in r["disliked_users"],
            "has_saved": user_id in r["saved_users"] 
        } 
        for r in reviews_db
    ]

@router.post("/reviews/action")
def review_action(req: ActionRequest):
    review = next((r for r in reviews_db if r["id"] == req.review_id), None)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    uid = req.user_id

    if req.action == "like":
        if uid in review["liked_users"]:
            review["liked_users"].remove(uid)
            review["likes"] -= 1
        else:
            if uid in review["disliked_users"]:
                review["disliked_users"].remove(uid)
                review["dislikes"] -= 1
            review["liked_users"].add(uid)
            review["likes"] += 1

    elif req.action == "dislike":
        if uid in review["disliked_users"]:
            review["disliked_users"].remove(uid)
            review["dislikes"] -= 1
        else:
            if uid in review["liked_users"]:
                review["liked_users"].remove(uid)
                review["likes"] -= 1
            review["disliked_users"].add(uid)
            review["dislikes"] += 1

    elif req.action == "save":
        if uid in review["saved_users"]:
            review["saved_users"].remove(uid)
        else:
            review["saved_users"].add(uid)

    return {"likes": review["likes"], "dislikes": review["dislikes"]}