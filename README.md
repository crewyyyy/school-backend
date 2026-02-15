# backend

FastAPI backend for EduFlow:
- admin auth (JWT)
- classes and points
- events and content blocks
- image upload with PNG normalization
- device registration for push
- push notifications (new/rescheduled/updated/canceled)
- test push endpoint and Telegram bot

## Stack

- Python 3.13
- FastAPI + Uvicorn
- SQLAlchemy 2 + Alembic
- Pillow (image conversion)
- Firebase Admin SDK (FCM)
- Aiogram (Telegram bot)

## Local run (without Docker)

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
python scripts/seed_classes.py
python scripts/seed_admin.py --login admin --password admin123
uvicorn app.main:app --reload --port 8000
```

Checks:

```powershell
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/system/info
```

## Tests

```powershell
.\.venv\Scripts\python -m pytest -q
```

## Key endpoints

- `POST /auth/login`
- `GET /events`
- `GET /events/{id}`
- `POST /events/{id}/publish`
- `DELETE /events/{id}`
- `POST /events/{id}/banner` (upload + PNG normalization)
- `POST /events/{id}/blocks/image` (upload + PNG normalization)
- `POST /devices/register`
- `GET /health`
- `GET /system/info`
- `GET /push/status`
- `POST /push/test` (admin auth required)

## Environment files

- `.env.example` - local development
- `.env.standalone.example` - standalone Docker
- `.env.deploy.example` - production deploy from GHCR

Important:
- Replace `JWT_SECRET` in production
- `FCM_SERVICE_ACCOUNT_JSON` must point to a valid service-account JSON inside the container

## Standalone Docker

```powershell
copy .env.standalone.example .env.standalone
docker compose -f docker-compose.standalone.yml --env-file .env.standalone up -d --build
```

Check:

```powershell
curl http://127.0.0.1:8000/health
```

## Deploy from GHCR

```powershell
copy .env.deploy.example .env.deploy
docker compose -f docker-compose.deploy.yml --env-file .env.deploy pull
docker compose -f docker-compose.deploy.yml --env-file .env.deploy up -d
```

Deploy services:
- `backend`
- `tg-bot`
- optional `watchtower` profile

Logs:

```powershell
docker compose -f docker-compose.deploy.yml --env-file .env.deploy logs -f backend
docker compose -f docker-compose.deploy.yml --env-file .env.deploy logs -f tg-bot
```

## Telegram bot

Script: `scripts/tg_push_bot.py`

Main environment variables:
- `TG_BOT_TOKEN`
- `TG_ADMIN_CHAT_ID`
- `TG_BOT_API_BASE_URL` (default: `http://backend:8000`)
- `TG_BOT_API_LOGIN`
- `TG_BOT_API_PASSWORD`

Supported bot commands:
- `/start`
- `/status`
- `/send <text>`
- `/notify <title> | <text>`

## Push troubleshooting

### Symptom: no push notifications

1. Check backend status:
   - `GET /system/info` -> `push_credentials_exists=true`
   - `GET /push/status` -> `credentials_exists=true`
2. Verify file inside container:
   - `/app/secrets/fcm-service-account.json`
3. Verify registered devices count:
   - `registered_devices > 0`
4. Run manual test:

```bash
BASE=http://127.0.0.1:8000
TOKEN=$(curl -s "$BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"login":"admin","password":"admin123"}' | jq -r .access_token)

curl -s -X POST "$BASE/push/test" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"EduFlow test","body":"Manual test push"}'
```

If response has `enabled=false` and `push_service_disabled_or_missing_credentials`, backend cannot read FCM credentials.

## Common issues

### `connection to server at "127.0.0.1", port 5432 failed`

Wrong `DATABASE_URL` for selected mode. Verify `.env.standalone`/`.env.deploy`.

### `Method Not Allowed` when deleting event

Client must call `DELETE /events/{event_id}` (not `POST`).

### Tunnel/domain problems

If `curl http://127.0.0.1:8000/health` works locally but domain does not:
- verify tunnel ingress target (`service: http://127.0.0.1:8000`)
- verify DNS and tunnel container health
