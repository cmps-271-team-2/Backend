from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core import firebase as firebase_core
from app.routers import admin, auth, feed, jobs, reviews

load_dotenv()
firebase_core.init_firebase()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth")
app.include_router(admin.router, prefix="/admin")
app.include_router(reviews.router)
app.include_router(feed.router)
app.include_router(jobs.router)


@app.get("/health")
def health():
    return {"status": "Backend running"}