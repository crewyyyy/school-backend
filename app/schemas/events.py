from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class EventCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    datetime_start: datetime | None = None
    location: str | None = Field(default=None, max_length=255)


class EventUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    datetime_start: datetime | None = None
    location: str | None = Field(default=None, max_length=255)


class EventCreateResponse(BaseModel):
    id: str
    status: str


class EventListItem(BaseModel):
    id: str
    title: str | None
    datetime_start: datetime | None
    location: str | None
    banner_image_url: str | None

    model_config = {"from_attributes": True}


class EventAdminListItem(BaseModel):
    id: str
    title: str | None
    datetime_start: datetime | None
    location: str | None
    banner_image_url: str | None
    status: str

    model_config = {"from_attributes": True}


class EventBlockCreateRequest(BaseModel):
    type: Literal["text", "image"]
    text: str | None = None
    image_url: str | None = None
    sort_order: int = Field(..., ge=0, le=10000)

    @model_validator(mode="after")
    def validate_payload(self):
        if self.type == "text" and not self.text:
            raise ValueError("text block requires text")
        if self.type == "image" and not self.image_url:
            raise ValueError("image block requires image_url")
        return self


class EventBlockReorderItem(BaseModel):
    block_id: str
    sort_order: int = Field(..., ge=0, le=10000)


class EventBlockOut(BaseModel):
    id: str
    event_id: str
    type: str
    text: str | None
    image_url: str | None
    sort_order: int

    model_config = {"from_attributes": True}


class EventDetail(BaseModel):
    id: str
    title: str | None
    datetime_start: datetime | None
    location: str | None
    banner_image_url: str | None
    status: str
    blocks: list[EventBlockOut]

    model_config = {"from_attributes": True}


class BannerUploadResponse(BaseModel):
    banner_image_url: str


class PublishResponse(BaseModel):
    status: str
