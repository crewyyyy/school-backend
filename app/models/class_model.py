from sqlalchemy import CheckConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import UUIDPrimaryKeyMixin


class SchoolClass(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "classes"
    __table_args__ = (CheckConstraint("grade >= 5 AND grade <= 11", name="ck_classes_grade_range"),)

    grade: Mapped[int] = mapped_column(Integer, nullable=False)
    letter: Mapped[str] = mapped_column(String(8), nullable=False)
    name: Mapped[str] = mapped_column(String(16), nullable=False, unique=True, index=True)
    total_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    point_transactions = relationship("PointTransaction", back_populates="school_class", cascade="all, delete-orphan")

