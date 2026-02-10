from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.device import Device
from app.schemas.devices import DeviceRegisterRequest, DeviceRegisterResponse

router = APIRouter(prefix="/devices", tags=["devices"])


@router.post("/register", response_model=DeviceRegisterResponse)
def register_device(payload: DeviceRegisterRequest, db: Session = Depends(get_db)):
    existing = db.scalar(select(Device).where(Device.fcm_token == payload.fcm_token))
    if existing:
        existing.platform = payload.platform
        db.add(existing)
    else:
        db.add(Device(fcm_token=payload.fcm_token, platform=payload.platform))
    db.commit()
    return DeviceRegisterResponse(ok=True)

