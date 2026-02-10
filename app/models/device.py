from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import CreatedAtMixin, UUIDPrimaryKeyMixin


class Device(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "devices"

    fcm_token: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True, index=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, default="android")

