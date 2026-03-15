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

Or via Makefile:

```bash
make install
```

3) Ensure `.env` is present and includes required configuration

```bash
# CORS origins
FRONTEND_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

# Resend API (for OTP email delivery)
RESEND_API_KEY=your_resend_api_key
RESEND_FROM_EMAIL=noreply@yourdomain.com

# Firebase configuration
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
FIREBASE_CLIENT_EMAIL=your-service-account@your-project.iam.gserviceaccount.com
FIREBASE_WEB_API_KEY=your-web-api-key
# ... (see .env.example for complete list)

# OTP expiry
OTP_EXP_MINUTES=10

# OpenAI embeddings
OPENAI_API_KEY=your_openai_api_key

# Pinecone vector store
PINECONE_API_KEY=your_pinecone_api_key
PINECONE_INDEX_NAME=unitok-posts
PINECONE_NAMESPACE=dev
PINECONE_CLOUD=aws
PINECONE_REGION=us-east-1
```

> **Note**: OTP emails are sent via Resend API over HTTPS (not SMTP). This ensures reliable delivery from cloud platforms like Render. See `.env.example` for all required variables.

Semantic post search now stores vectors and post metadata in Pinecone. The backend will create the configured Pinecone index automatically if it does not exist yet.

4) Start the API

```bash
uvicorn app.main:app --reload --port 8000
```

Or via Makefile:

```bash
make run
```

Install + run in one step:

```bash
make dev
```

Health check:
- http://127.0.0.1:8000/

## Seeding courses

The seed script now lives under `app/scripts` and the dataset under `app/data`.

From `Backend/`:

```bash
python app/scripts/seed_courses.py
```
