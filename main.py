from fastapi import FastAPI
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from core.firebase_admin import init_firebase_admin
from auth.routes import router as auth_router
from pathlib import Path

# Load environment variables from backend/.env
# Using resolve() ensures it works even during uvicorn reload
backend_dir = Path(__file__).resolve().parent
env_file = backend_dir / ".env"
load_dotenv(env_file)

init_firebase_admin()

app = FastAPI()
# Language: Python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/auth")

@app.get("/")
def health():
    return {"Status": "Backend running"}