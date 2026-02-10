from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import CreatedAtMixin, UUIDPrimaryKeyMixin


class PointTransaction(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "point_transactions"

    class_id: Mapped[str] = mapped_column(String(36), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    delta_points: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(String(512), nullable=False)
    created_by_admin_id: Mapped[str] = mapped_column(String(36), ForeignKey("admins.id", ondelete="RESTRICT"), nullable=False)

    school_class = relationship("SchoolClass", back_populates="point_transactions")
    created_by_admin = relationship("Admin", back_populates="point_transactions")

