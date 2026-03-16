# Backend (FastAPI)

## Local development

1) Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

2) Install dependencies

```bash
pip install -r requirements.txt
```

3) Ensure `.env` is present and includes required configuration

See `.env.example` for all required fields. Key groups:

- Firebase admin credentials and web API key
- Resend email variables
- OpenAI + Pinecone variables for semantic indexing
- Redis URL for Celery broker/result backend
- Gemini API key/model for moderation

4) Start API + worker

```bash
uvicorn app.main:app --reload --port 8000
celery -A app.jobs.celery_app.celery_app worker --loglevel=info --pool=threads --concurrency=3
```

## Redis + Celery flow

- `POST /posts` now creates the post and queues moderation/indexing asynchronously.
- `POST /process_post` queues moderation + indexing for an existing post id.
- `POST /upload_post` queues single-post indexing.
- `POST /update_posts_index` queues full re-index.
- `GET /tasks/{task_id}` returns Celery task status/result.

## Docker (Alpine)

Build and run API + Redis + Celery workers locally:

```bash
docker compose -f infra/docker-compose.dev.yml up --build -d --scale celery-worker=4
```

Each worker runs with thread pool concurrency of 3.
Scaling to 4 replicas gives the requested 4 workers with 3 threads each.

## VPS deployment via GitHub Actions

Use separate workflows:

- `.github/workflows/deploy-vps-main.yml` (branch `main`, environment `production`)
- `.github/workflows/deploy-vps-dev.yml` (branch `env`, environment `development`)

Set these GitHub repository settings:

- Variables (`Settings > Secrets and variables > Actions > Variables`):
	- `VPS_HOST`
	- `VPS_USER`
	- `VPS_PORT` (optional, default 22)
	- `VPS_APP_PATH` (for example `/opt/backend`)
	- `FRONTEND_ORIGINS`
	- `OTP_EXP_MINUTES`
	- `PINECONE_INDEX_NAME`
	- `PINECONE_NAMESPACE`
	- `PINECONE_CLOUD`
	- `PINECONE_REGION`
	- `REDIS_URL`
	- `GEMINI_MODEL`

- Secrets (`Settings > Secrets and variables > Actions > Secrets`):
	- `VPS_SSH_KEY`
	- `FIREBASE_TYPE`
	- `FIREBASE_PROJECT_ID`
	- `FIREBASE_PRIVATE_KEY_ID`
	- `FIREBASE_PRIVATE_KEY`
	- `FIREBASE_CLIENT_EMAIL`
	- `FIREBASE_CLIENT_ID`
	- `FIREBASE_AUTH_URI`
	- `FIREBASE_TOKEN_URI`
	- `FIREBASE_AUTH_PROVIDER_X509_CERT_URL`
	- `FIREBASE_CLIENT_X509_CERT_URL`
	- `FIREBASE_UNIVERSE_DOMAIN`
	- `FIREBASE_WEB_API_KEY`
	- `RESEND_API_KEY`
	- `RESEND_FROM_EMAIL`
	- `OPENAI_API_KEY`
	- `PINECONE_API_KEY`
	- `GCP_GEMINI_API_KEY`

Each workflow writes these values into `.env` on the VPS and starts services with:

```bash
docker compose -f infra/docker-compose.main.yml up -d --build --scale celery-worker=4 --remove-orphans
```

For dev deployments, the workflow uses `infra/docker-compose.dev.yml`.

## Local deploy to VPS (manual test)

You can deploy directly from your machine (without GitHub Actions):

```bash
export VPS_HOST=your.server.ip
export VPS_USER=root
export VPS_PORT=22
export VPS_APP_PATH=/opt/backend
export SSH_KEY="$(cat .ssh/unitok)"
export DEPLOY_ENV=dev
export CELERY_WORKER_SCALE=4

make vps-up
```

This command:

- syncs your project to the VPS via `rsync`
- uploads local `.env` to the VPS app path
- runs `docker compose down` then `docker compose up -d --build` remotely

To stop services on the VPS:

```bash
make vps-down
```

## Seeding courses

```bash
python app/scripts/seed_courses.py
```
