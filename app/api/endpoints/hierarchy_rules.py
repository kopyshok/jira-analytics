"""Hierarchy rule CRUD endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.hierarchy_rule import HierarchyRule
from app.repositories.base import BaseRepository
from app.services.backlog_service import service_epic_backlog_ids, switch_off_new_service_epics

router = APIRouter()


# === Schemas ===

class HierarchyRuleResponse(BaseModel):
    id: str
    priority: int
    project_key: Optional[str] = None
    issue_type: Optional[str] = None
    require_no_parent: bool
    require_parent: bool = False
    is_container: bool
    is_enabled: bool
    description: Optional[str] = None

    class Config:
        from_attributes = True


class HierarchyRuleCreate(BaseModel):
    priority: int = Field(ge=0)
    project_key: Optional[str] = None
    issue_type: Optional[str] = None
    require_no_parent: bool = False
    require_parent: bool = False
    is_container: bool
    is_enabled: bool = True
    description: Optional[str] = None


class HierarchyRuleUpdate(BaseModel):
    priority: Optional[int] = Field(default=None, ge=0)
    project_key: Optional[str] = None
    issue_type: Optional[str] = None
    require_no_parent: Optional[bool] = None
    require_parent: Optional[bool] = None
    is_container: Optional[bool] = None
    is_enabled: Optional[bool] = None
    description: Optional[str] = None


def _check_parent_predicates(require_no_parent: bool, require_parent: bool) -> None:
    """«Только без родителя» и «только с родителем» вместе не имеют смысла."""
    if require_no_parent and require_parent:
        raise HTTPException(
            status_code=400,
            detail="Условие по родителю может быть только одно: без родителя ИЛИ с родителем",
        )


class ReorderRequest(BaseModel):
    ids: List[str]


# === Endpoints ===

@router.get("", response_model=List[HierarchyRuleResponse])
def list_rules(db: Session = Depends(get_db)):
    stmt = (
        select(HierarchyRule)
        .order_by(HierarchyRule.priority.asc(), HierarchyRule.created_at.asc())
    )
    return list(db.execute(stmt).scalars().all())


@router.post("", response_model=HierarchyRuleResponse, status_code=status.HTTP_201_CREATED)
def create_rule(body: HierarchyRuleCreate, db: Session = Depends(get_db)):
    _check_parent_predicates(body.require_no_parent, body.require_parent)
    # Снимок служебных эпиков до правки: ставшие служебными выключаем из плана.
    before = service_epic_backlog_ids(db)
    repo = BaseRepository(HierarchyRule, db)
    rule = repo.create(body.model_dump())
    switch_off_new_service_epics(db, before)
    db.commit()
    return rule


@router.patch("/{rule_id}", response_model=HierarchyRuleResponse)
def update_rule(rule_id: str, body: HierarchyRuleUpdate, db: Session = Depends(get_db)):
    rule = db.get(HierarchyRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Правило не найдено")
    changes = body.model_dump(exclude_unset=True)
    _check_parent_predicates(
        changes.get("require_no_parent", rule.require_no_parent),
        changes.get("require_parent", rule.require_parent),
    )
    before = service_epic_backlog_ids(db)
    for field, value in changes.items():
        setattr(rule, field, value)
    db.flush()
    switch_off_new_service_epics(db, before)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{rule_id}")
def delete_rule(rule_id: str, db: Session = Depends(get_db)):
    rule = db.get(HierarchyRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Правило не найдено")
    before = service_epic_backlog_ids(db)
    db.delete(rule)
    db.flush()
    switch_off_new_service_epics(db, before)
    db.commit()
    return {"status": "deleted"}


@router.post("/reorder", response_model=List[HierarchyRuleResponse])
def reorder_rules(body: ReorderRequest, db: Session = Depends(get_db)):
    before = service_epic_backlog_ids(db)
    for index, rule_id in enumerate(body.ids):
        rule = db.get(HierarchyRule, rule_id)
        if not rule:
            raise HTTPException(status_code=404, detail=f"Правило {rule_id} не найдено")
        rule.priority = (index + 1) * 10
    db.flush()
    switch_off_new_service_epics(db, before)
    db.commit()
    stmt = (
        select(HierarchyRule)
        .order_by(HierarchyRule.priority.asc(), HierarchyRule.created_at.asc())
    )
    return list(db.execute(stmt).scalars().all())
