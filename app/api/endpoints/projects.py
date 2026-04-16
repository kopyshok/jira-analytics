"""Projects API endpoints.

Список синхронизированных проектов для использования во фронтенде.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project


router = APIRouter()


class ProjectResponse(BaseModel):
    id: str
    key: str
    name: str
    is_active: bool

    model_config = {"from_attributes": True}


@router.get("", response_model=List[ProjectResponse])
def list_projects(
    is_active: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
):
    """Список синхронизированных проектов."""
    query = db.query(Project).order_by(Project.key)
    if is_active is not None:
        query = query.filter(Project.is_active == is_active)
    return query.all()
