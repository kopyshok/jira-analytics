from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth_deps import get_current_user
from app.database import get_db
from app.models.user import User

router = APIRouter()


class PeriodPayload(BaseModel):
    year: int | None = None
    quarter: int | None = None
    month: int | None = None


class ColumnsPayload(BaseModel):
    columns: list[str]


@router.get("/me/period")
def get_my_period(current_user: User = Depends(get_current_user)):
    return current_user.selected_period


@router.put("/me/period")
def set_my_period(
    payload: PeriodPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user.selected_period = payload.model_dump(exclude_none=True)
    db.commit()
    return {"ok": True}


@router.get("/me/analytics-columns")
def get_my_columns(current_user: User = Depends(get_current_user)):
    return {"columns": current_user.analytics_columns}


@router.put("/me/analytics-columns")
def set_my_columns(
    payload: ColumnsPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user.analytics_columns = payload.columns
    db.commit()
    return {"ok": True}
