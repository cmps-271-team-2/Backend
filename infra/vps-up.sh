#!/usr/bin/env bash

set -euo pipefail

# Local -> VPS deploy helper for quick manual testing.
# Required env vars:
#   VPS_HOST
#   VPS_USER
#   SSH_KEY
# Optional env vars:
#   VPS_PORT (default: 22)
#   VPS_APP_PATH (default: /opt/backend)
#   DEPLOY_ENV (default: dev, allowed: dev|prod|main)
#   CELERY_WORKER_SCALE (default: 4)

if [[ -z "${VPS_HOST:-}" || -z "${VPS_USER:-}" ]]; then
  echo "Error: VPS_HOST and VPS_USER must be set."
  exit 1
fi

if [[ -z "${SSH_KEY:-}" ]]; then
  echo "Error: SSH_KEY must be set."
  exit 1
fi

VPS_PORT="${VPS_PORT:-22}"
VPS_APP_PATH="${VPS_APP_PATH:-/opt/backend}"
DEPLOY_ENV="${DEPLOY_ENV:-dev}"
CELERY_WORKER_SCALE="${CELERY_WORKER_SCALE:-4}"

case "$DEPLOY_ENV" in
  dev)
    COMPOSE_FILE="infra/docker-compose.dev.yml"
    ;;
  prod|main)
    COMPOSE_FILE="infra/docker-compose.main.yml"
    ;;
  *)
    echo "Error: DEPLOY_ENV must be 'dev' or 'prod' (legacy: 'main')."
    exit 1
    ;;
esac

if [[ ! -f ".env" ]]; then
  echo "Error: local .env file not found."
  exit 1
fi

TMP_SSH_KEY_FILE="$(mktemp)"
trap 'rm -f "$TMP_SSH_KEY_FILE"' EXIT
printf '%b\n' "$SSH_KEY" > "$TMP_SSH_KEY_FILE"
chmod 600 "$TMP_SSH_KEY_FILE"

SSH_OPTS=(
  -i "$TMP_SSH_KEY_FILE"
  -p "$VPS_PORT"
  -o StrictHostKeyChecking=accept-new
)

SCP_OPTS=(
  -i "$TMP_SSH_KEY_FILE"
  -P "$VPS_PORT"
  -o StrictHostKeyChecking=accept-new
)

echo "Creating remote app directory: $VPS_APP_PATH"
ssh "${SSH_OPTS[@]}" "$VPS_USER@$VPS_HOST" "mkdir -p '$VPS_APP_PATH'"

echo "Syncing project to VPS..."
rsync -az --delete \
  -e "ssh -i $TMP_SSH_KEY_FILE -p $VPS_PORT -o StrictHostKeyChecking=accept-new" \
  --exclude ".git" \
  --exclude ".venv" \
  --exclude "__pycache__" \
  --exclude ".pytest_cache" \
  ./ "$VPS_USER@$VPS_HOST:$VPS_APP_PATH/"

echo "Uploading .env to VPS..."
scp "${SCP_OPTS[@]}" .env "$VPS_USER@$VPS_HOST:$VPS_APP_PATH/.env"

echo "Deploying with Docker Compose on VPS..."
ssh "${SSH_OPTS[@]}" "$VPS_USER@$VPS_HOST" "
  set -euo pipefail
  cd '$VPS_APP_PATH'
  docker compose -f '$COMPOSE_FILE' down --remove-orphans
  docker compose -f '$COMPOSE_FILE' up -d --build --scale celery-worker='$CELERY_WORKER_SCALE' --remove-orphans
  docker compose -f '$COMPOSE_FILE' ps
"

echo "VPS deploy complete."