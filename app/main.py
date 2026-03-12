import os

from fastapi import FastAPI
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from app.core.firebase_admin import init_firebase_admin
from app.auth.routes import router as auth_router
from app.admin.routes import router as admin_router
from app.feed.routes import router as feed_router

load_dotenv()

init_firebase_admin()

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

app.include_router(auth_router, prefix="/auth")
app.include_router(admin_router, prefix="/admin")
app.include_router(feed_router)
