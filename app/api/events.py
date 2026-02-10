from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_admin
from app.db.session import get_db
from app.models.admin import Admin
from app.models.event import Event
from app.models.event_block import EventBlock
from app.schemas.events import (
    BannerUploadResponse,
    EventAdminListItem,
    EventBlockCreateRequest,
    EventBlockOut,
    EventBlockReorderItem,
    EventCreateRequest,
    EventCreateResponse,
    EventDetail,
    EventListItem,
    EventUpdateRequest,
    PublishResponse,
)
from app.services.push import PushService
from app.services.storage import StorageService

router = APIRouter(prefix="/events", tags=["events"])

storage_service = StorageService()
push_service = PushService()


@router.post("", response_model=EventCreateResponse)
def create_event(
    payload: EventCreateRequest,
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
):
    event = Event(
        title=payload.title,
        datetime_start=payload.datetime_start,
        location=payload.location,
        status="draft",
        created_by_admin_id=admin.id,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return EventCreateResponse(id=event.id, status=event.status)


@router.patch("/{event_id}", response_model=EventCreateResponse)
def update_event(
    event_id: str,
    payload: EventUpdateRequest,
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    if payload.title is not None:
        event.title = payload.title
    if payload.datetime_start is not None:
        event.datetime_start = payload.datetime_start
    if payload.location is not None:
        event.location = payload.location

    db.add(event)
    db.commit()
    db.refresh(event)
    return EventCreateResponse(id=event.id, status=event.status)


@router.post("/{event_id}/banner", response_model=BannerUploadResponse)
async def upload_banner(
    event_id: str,
    banner: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    banner_url = await storage_service.save_upload(banner, prefix=f"events/{event_id}/banner")
    event.banner_image_url = banner_url
    db.add(event)
    db.commit()
    return BannerUploadResponse(banner_image_url=banner_url)


@router.post("/{event_id}/blocks/image", response_model=EventBlockOut)
async def upload_image_block(
    event_id: str,
    sort_order: int = Query(..., ge=0, le=10000),
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    image_url = await storage_service.save_upload(image, prefix=f"events/{event_id}/blocks")
    block = EventBlock(
        event_id=event.id,
        type="image",
        text=None,
        image_url=image_url,
        sort_order=sort_order,
    )
    db.add(block)
    db.commit()
    db.refresh(block)
    return block


@router.post("/{event_id}/blocks", response_model=EventBlockOut)
def add_block(
    event_id: str,
    payload: EventBlockCreateRequest,
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    block = EventBlock(
        event_id=event.id,
        type=payload.type,
        text=payload.text,
        image_url=payload.image_url,
        sort_order=payload.sort_order,
    )
    db.add(block)
    db.commit()
    db.refresh(block)
    return block


@router.delete("/{event_id}/blocks/{block_id}")
def delete_block(
    event_id: str,
    block_id: str,
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    block = db.get(EventBlock, block_id)
    if not block or block.event_id != event_id:
        raise HTTPException(status_code=404, detail="Block not found")

    db.delete(block)
    db.commit()
    return {"ok": True}


@router.put("/{event_id}/blocks/reorder")
def reorder_blocks(
    event_id: str,
    payload: list[EventBlockReorderItem],
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    blocks = db.scalars(select(EventBlock).where(EventBlock.event_id == event_id)).all()
    block_map = {block.id: block for block in blocks}
    for item in payload:
        if item.block_id not in block_map:
            raise HTTPException(status_code=400, detail=f"Block {item.block_id} does not belong to event")
        block_map[item.block_id].sort_order = item.sort_order

    db.commit()
    return {"ok": True}


@router.post("/{event_id}/publish", response_model=PublishResponse)
def publish_event(
    event_id: str,
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    missing_fields: list[str] = []
    if not event.title:
        missing_fields.append("title")
    if not event.datetime_start:
        missing_fields.append("datetime_start")
    if not event.location:
        missing_fields.append("location")
    if not event.banner_image_url:
        missing_fields.append("banner_image_url")

    if missing_fields:
        raise HTTPException(
            status_code=400,
            detail={"error": "missing_required_fields", "fields": missing_fields},
        )

    event.status = "published"
    db.add(event)
    db.commit()
    db.refresh(event)

    push_service.send_event_published(event, db)
    return PublishResponse(status=event.status)


@router.get("/admin", response_model=list[EventAdminListItem])
def list_events_admin(
    status_value: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    stmt = select(Event).order_by(Event.created_at.desc()).limit(limit)
    if status_value and status_value != "all":
        stmt = stmt.where(Event.status == status_value)
    rows = db.scalars(stmt).all()
    return rows


@router.get("", response_model=list[EventListItem])
def list_events(
    from_value: str | None = Query(default=None, alias="from"),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    stmt = (
        select(Event)
        .where(Event.status == "published")
        .order_by(Event.datetime_start.asc().nulls_last(), Event.created_at.asc())
        .limit(limit)
    )
    if from_value:
        if from_value == "now":
            dt = datetime.now(UTC)
        else:
            try:
                dt = datetime.fromisoformat(from_value)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="Invalid from datetime") from exc
        stmt = stmt.where(Event.datetime_start >= dt)

    rows = db.scalars(stmt).all()
    return rows


@router.get("/{event_id}", response_model=EventDetail)
def event_details(event_id: str, db: Session = Depends(get_db)):
    stmt = (
        select(Event)
        .where(Event.id == event_id)
        .options(selectinload(Event.blocks))
    )
    event = db.scalar(stmt)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    blocks = sorted(event.blocks, key=lambda item: item.sort_order)
    return EventDetail(
        id=event.id,
        title=event.title,
        datetime_start=event.datetime_start,
        location=event.location,
        banner_image_url=event.banner_image_url,
        status=event.status,
        blocks=[EventBlockOut.model_validate(block) for block in blocks],
    )
