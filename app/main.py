import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from app.core import firebase as firebase_core
from app.routers import admin, auth, feed, jobs, reviews

firebase_core.init_firebase()

app = FastAPI()

origins_env = os.getenv(
    "FRONTEND_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,https://unitok.app,https://www.unitok.app,https://unitok-rouge.vercel.app",
)
origins = [
    origin.strip().rstrip("/")
    for origin in origins_env.split(",")
    if origin.strip().rstrip("/")
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth")
app.include_router(admin.router, prefix="/admin")

app.include_router(reviews.router)

@app.get("/health")
def health():
    return {"Status": "Backend running"}


app.include_router(feed.router)
app.include_router(jobs.router)
