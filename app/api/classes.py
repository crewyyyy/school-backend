from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db.session import get_db
from app.models.admin import Admin
from app.models.class_model import SchoolClass
from app.models.point_transaction import PointTransaction
from app.schemas.classes import ClassOut, PointHistoryItem, PointOperationRequest, PointOperationResponse

router = APIRouter(prefix="/classes", tags=["classes"])


@router.get("", response_model=list[ClassOut], dependencies=[Depends(get_current_admin)])
def list_classes(db: Session = Depends(get_db)):
    rows = db.scalars(select(SchoolClass).order_by(SchoolClass.grade, SchoolClass.letter)).all()
    return rows


@router.post("/{class_id}/points", response_model=PointOperationResponse)
def add_points(
    class_id: str,
    payload: PointOperationRequest,
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
):
    school_class = db.get(SchoolClass, class_id)
    if not school_class:
        raise HTTPException(status_code=404, detail="Class not found")

    transaction = PointTransaction(
        class_id=school_class.id,
        delta_points=payload.delta_points,
        category=payload.category,
        reason=payload.reason,
        created_by_admin_id=admin.id,
    )
    school_class.total_points += payload.delta_points
    db.add(transaction)
    db.add(school_class)
    db.commit()
    db.refresh(school_class)
    return PointOperationResponse(ok=True, total_points=school_class.total_points)


@router.get("/{class_id}/points/history", response_model=list[PointHistoryItem])
def points_history(
    class_id: str,
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    school_class = db.get(SchoolClass, class_id)
    if not school_class:
        raise HTTPException(status_code=404, detail="Class not found")

    rows = db.scalars(
        select(PointTransaction)
        .where(PointTransaction.class_id == class_id)
        .order_by(PointTransaction.created_at.desc())
    ).all()
    return rows

