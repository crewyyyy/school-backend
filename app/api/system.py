from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.core.config import get_settings
from app.db.session import get_db
from app.models.admin import Admin
from app.models.device import Device
from app.services.push import PushService

router = APIRouter(tags=["system"])
push_service = PushService()


class PushTestRequest(BaseModel):
    title: str = Field(default="EduFlow test notification", max_length=120)
    body: str = Field(default="If you see this message, push notifications are configured correctly.", max_length=500)


@router.get("/health")
def health():
    settings = get_settings()
    return {"status": "ok", "version": settings.app_version}


@router.get("/system/info")
def system_info(db: Session = Depends(get_db)):
    settings = get_settings()
    creds_path = Path(settings.fcm_service_account_json)
    devices_count = db.scalar(select(func.count()).select_from(Device)) or 0
    return {
        "app_name": settings.app_name,
        "app_env": settings.app_env,
        "app_version": settings.app_version,
        "push_topic": settings.fcm_topic,
        "push_credentials_exists": creds_path.exists(),
        "registered_devices": devices_count,
    }


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


@router.post("/push/test")
def push_test(
    payload: PushTestRequest,
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    return push_service.send_test_notification(
        title=payload.title,
        body=payload.body,
        db=db,
    )
