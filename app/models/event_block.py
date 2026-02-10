from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import UUIDPrimaryKeyMixin


class EventBlock(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "event_blocks"

    event_id: Mapped[str] = mapped_column(String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False)  # text | image
    text: Mapped[str | None] = mapped_column(String, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)

    event = relationship("Event", back_populates="blocks")

