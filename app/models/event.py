from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import CreatedAtMixin, UUIDPrimaryKeyMixin


class Event(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "events"

    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    datetime_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    banner_image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", index=True)
    created_by_admin_id: Mapped[str] = mapped_column(String(36), ForeignKey("admins.id", ondelete="RESTRICT"), nullable=False)

    blocks = relationship("EventBlock", back_populates="event", cascade="all, delete-orphan")
    created_by_admin = relationship("Admin", back_populates="events")

