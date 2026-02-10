from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.device import Device

router = APIRouter(tags=["system"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/push/status")
def push_status(db: Session = Depends(get_db)):
    settings = get_settings()
    creds_path = Path(settings.fcm_service_account_json)
    devices_count = db.scalar(select(func.count()).select_from(Device)) or 0
    return {
        "fcm_service_account_json": str(creds_path),
        "credentials_exists": creds_path.exists(),
        "topic": settings.fcm_topic,
        "registered_devices": devices_count,
    }
