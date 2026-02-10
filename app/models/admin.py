from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import UUIDPrimaryKeyMixin


class Admin(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "admins"

    login: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="admin")

    point_transactions = relationship("PointTransaction", back_populates="created_by_admin")
    events = relationship("Event", back_populates="created_by_admin")

