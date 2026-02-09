# Backend (FastAPI)

## Local development

1) Create and activate a virtual environment

```bash
python -m venv venv

# Windows (PowerShell)
venv\Scripts\Activate.ps1

# Windows (cmd)
venv\Scripts\activate.bat
```

2) Install dependencies

```bash
pip install -r requirements.txt
```

3) Ensure `.env` is present and includes CORS origins

```bash
FRONTEND_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

4) Start the API

```bash
uvicorn app.main:app --reload --port 8000
```

Health check:
- http://127.0.0.1:8000/
