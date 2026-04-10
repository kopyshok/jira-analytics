"""Backlog items API endpoints.

Управление квартальным бэклогом: задачи-кандидаты, которые могут
войти в сценарии квартального планирования.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BacklogItem
from app.repositories.base import BaseRepository


router = APIRouter()


# === Schemas ===

class BacklogItemCreate(BaseModel):
    title: str
    project_id: Optional[str] = None
    quarter: Optional[str] = Field(default=None, max_length=10)
    year: Optional[int] = None
    estimate_hours: Optional[float] = Field(default=None, ge=0)
    priority: Optional[int] = None


class BacklogItemUpdate(BaseModel):
    title: Optional[str] = None
    project_id: Optional[str] = None
    quarter: Optional[str] = Field(default=None, max_length=10)
    year: Optional[int] = None
    estimate_hours: Optional[float] = Field(default=None, ge=0)
    priority: Optional[int] = None


class BacklogItemResponse(BaseModel):
    id: str
    title: str
    project_id: Optional[str] = None
    quarter: Optional[str] = None
    year: Optional[int] = None
    estimate_hours: Optional[float] = None
    priority: Optional[int] = None

    class Config:
        from_attributes = True


# === CRUD ===

@router.get("", response_model=List[BacklogItemResponse])
async def list_backlog_items(
    year: Optional[int] = Query(None),
    quarter: Optional[str] = Query(None, max_length=10),
    project_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Список элементов бэклога с фильтрами по году/кварталу/проекту.

    Сортировка: сначала по priority (nulls last), затем по title.
    """
    query = db.query(BacklogItem)
    if year is not None:
        query = query.filter(BacklogItem.year == year)
    if quarter is not None:
        query = query.filter(BacklogItem.quarter == quarter)
    if project_id is not None:
        query = query.filter(BacklogItem.project_id == project_id)

    items = query.all()
    items.sort(
        key=lambda i: (
            i.priority is None,
            i.priority if i.priority is not None else 0,
            i.title or "",
        )
    )
    return items


@router.post("", response_model=BacklogItemResponse, status_code=201)
async def create_backlog_item(
    data: BacklogItemCreate,
    db: Session = Depends(get_db),
):
    """Добавить элемент в бэклог."""
    repo = BaseRepository(BacklogItem, db)
    item = repo.create(data.model_dump())
    db.commit()
    db.refresh(item)
    return item


@router.get("/{item_id}", response_model=BacklogItemResponse)
async def get_backlog_item(
    item_id: str,
    db: Session = Depends(get_db),
):
    """Получить один элемент бэклога по id."""
    repo = BaseRepository(BacklogItem, db)
    item = repo.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Backlog item not found")
    return item


@router.patch("/{item_id}", response_model=BacklogItemResponse)
async def update_backlog_item(
    item_id: str,
    data: BacklogItemUpdate,
    db: Session = Depends(get_db),
):
    """Частичное обновление элемента бэклога."""
    repo = BaseRepository(BacklogItem, db)
    item = repo.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Backlog item not found")

    patch = data.model_dump(exclude_unset=True)
    if not patch:
        return item

    updated = repo.update(item, patch)
    db.commit()
    db.refresh(updated)
    return updated


@router.delete("/{item_id}")
async def delete_backlog_item(
    item_id: str,
    db: Session = Depends(get_db),
):
    """Удалить элемент бэклога."""
    repo = BaseRepository(BacklogItem, db)
    item = repo.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Backlog item not found")
    repo.delete(item)
    db.commit()
    return {"status": "deleted", "id": item_id}
