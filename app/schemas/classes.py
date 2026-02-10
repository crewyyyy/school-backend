from datetime import datetime

from pydantic import BaseModel, Field


class ClassOut(BaseModel):
    id: str
    name: str
    grade: int
    letter: str
    total_points: int

    model_config = {"from_attributes": True}


class PointOperationRequest(BaseModel):
    delta_points: int = Field(..., ge=-1000, le=1000)
    category: str = Field(..., min_length=1, max_length=128)
    reason: str = Field(..., min_length=1, max_length=512)


class PointOperationResponse(BaseModel):
    ok: bool
    total_points: int


class PointHistoryItem(BaseModel):
    id: str
    class_id: str
    delta_points: int
    category: str
    reason: str
    created_at: datetime
    created_by_admin_id: str

    model_config = {"from_attributes": True}

