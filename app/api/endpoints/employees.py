"""Employees API endpoints.

Список сотрудников для использования во фронтенде (выпадающие списки и т.п.).
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Employee


router = APIRouter()


class EmployeeResponse(BaseModel):
    id: str
    display_name: str
    email: Optional[str] = None
    is_active: bool

    model_config = {"from_attributes": True}


@router.get("", response_model=List[EmployeeResponse])
def list_employees(
    is_active: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
):
    """Список сотрудников."""
    query = db.query(Employee).order_by(Employee.display_name)
    if is_active is not None:
        query = query.filter(Employee.is_active == is_active)
    return query.all()
