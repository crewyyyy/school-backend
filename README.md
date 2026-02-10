# backend

FastAPI backend for:

- admin auth (JWT),
- classes and points,
- events and media upload,
- mobile device registration for push.

## Environment

Copy `.env.example` to `.env` and adjust values.

## Run

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
python scripts/seed_classes.py
python scripts/seed_admin.py --login admin --password admin123
uvicorn app.main:app --reload --port 8000
```

## Tests

```powershell
.\.venv\Scripts\python -m pytest -q
```

## Standalone server container (single service)

This mode runs backend in one container with:
- SQLite DB in Docker volume,
- local media storage in Docker volume,
- automatic migrations and seed on startup.

### 1) Prepare env file

```powershell
cd backend
copy .env.standalone.example .env.standalone
```

Linux/macOS:

```bash
cd backend
cp .env.standalone.example .env.standalone
```

Edit `.env.standalone`:
- set `PUBLIC_HOST` to your server public IP or domain,
- set `HOST_PORT` if `8000` is already used on server,
- set strong `JWT_SECRET`,
- optionally change admin credentials.
- do not reuse `.env.example` for standalone mode.

For push notifications:
- place Firebase service account file at `backend/secrets/fcm-service-account.json`,
- keep `FCM_SERVICE_ACCOUNT_JSON=/app/secrets/fcm-service-account.json` (default),
- optional: change `FCM_TOPIC`.

### 2) Build and run

```powershell
docker compose -f docker-compose.standalone.yml --env-file .env.standalone up -d --build
```

If you previously started with wrong env values, reset and start clean:

```powershell
docker compose -f docker-compose.standalone.yml --env-file .env.standalone down
docker compose -f docker-compose.standalone.yml --env-file .env.standalone up -d --build
```

### 3) Verify

```powershell
curl http://<SERVER_IP>:<HOST_PORT>/health
```

Expected: `{"status":"ok"}`.

For push diagnostics:

```powershell
curl http://<SERVER_IP>:<HOST_PORT>/push/status
```

### 4) Client connection values

- Admin PC client API URL: `http://<SERVER_IP>:<HOST_PORT>`
- Mobile client API base URL: `http://<SERVER_IP>:<HOST_PORT>/`

If server has firewall, open TCP port used in `HOST_PORT` (default: `8000`).

### Troubleshooting: `connection to server at "127.0.0.1", port 5432 failed`

This means standalone started with Postgres URL (`DATABASE_URL=...localhost:5432...`) instead of SQLite volume DB.

Fix:
1. Ensure you run exactly:
   `docker compose -f docker-compose.standalone.yml --env-file .env.standalone up -d --build`
2. In `.env.standalone`, keep `STANDALONE_DATABASE_URL` empty or set it to SQLite.
3. Restart container stack.

### Troubleshooting: publish works but push notifications do not arrive

1. Check backend logs:
   `docker compose -f docker-compose.standalone.yml --env-file .env.standalone logs -f backend`
2. On startup you should see:
   `FCM_SERVICE_ACCOUNT_JSON=... (exists=True)`.
3. If `exists=False`, mount and provide Firebase service account JSON:
   `backend/secrets/fcm-service-account.json`.
4. Restart stack after adding the file.

## GHCR deploy with auto-update (no manual copy on server)

This flow publishes Docker image from GitHub Actions and deploys by pulling image tag on server.

### 1) CI image publishing to GHCR

Workflow file: `.github/workflows/backend-image.yml`

- image name: `ghcr.io/<owner>/school-backend`
- tags:
  - `latest` (default branch),
  - `sha-<commit>`

### 2) Server deploy compose (image only)

Files:
- `docker-compose.deploy.yml`
- `.env.deploy.example`

Prepare env:

```bash
cd backend
cp .env.deploy.example .env.deploy
```

Set values in `.env.deploy`:
- `BACKEND_IMAGE=ghcr.io/crewyyyy/school-backend:latest`
- `PUBLIC_HOST=<SERVER_IP_OR_DOMAIN>`
- `JWT_SECRET=<strong_secret>`

First deploy:

```bash
docker compose -f docker-compose.deploy.yml --env-file .env.deploy pull
docker compose -f docker-compose.deploy.yml --env-file .env.deploy up -d
```

### 3) Auto-update options

Option A: Watchtower (recommended):

```bash
docker compose -f docker-compose.deploy.yml --env-file .env.deploy --profile watchtower up -d watchtower
```

Option B: cron using update script:

```bash
chmod +x backend/scripts/deploy_update.sh
```

Run every 5 minutes:

```bash
*/5 * * * * /bin/bash /path/to/project/backend/scripts/deploy_update.sh >/var/log/school-api-update.log 2>&1
```
