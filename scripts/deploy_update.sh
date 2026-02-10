#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env.deploy"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.deploy.yml"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "[ERROR] Missing ${ENV_FILE}. Create it from .env.deploy.example first."
  exit 1
fi

docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" pull backend
docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d backend
docker image prune -f >/dev/null 2>&1 || true

echo "[OK] Backend updated from registry image."
