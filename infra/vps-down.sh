#!/usr/bin/env bash

set -euo pipefail

# Required env vars:
#   VPS_HOST
#   VPS_USER
#   SSH_KEY
# Optional env vars:
#   VPS_PORT (default: 22)
#   VPS_APP_PATH (default: /opt/backend)
#   DEPLOY_ENV (default: dev, allowed: dev|prod|main)

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

TMP_SSH_KEY_FILE="$(mktemp)"
trap 'rm -f "$TMP_SSH_KEY_FILE"' EXIT
printf '%b\n' "$SSH_KEY" > "$TMP_SSH_KEY_FILE"
chmod 600 "$TMP_SSH_KEY_FILE"

ssh \
  -i "$TMP_SSH_KEY_FILE" \
  -p "$VPS_PORT" \
  -o StrictHostKeyChecking=accept-new \
  "$VPS_USER@$VPS_HOST" \
  "cd '$VPS_APP_PATH' && docker compose -f '$COMPOSE_FILE' down --remove-orphans"

echo "VPS services stopped."
