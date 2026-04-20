"""Backlog items API endpoints.

Управление квартальным бэклогом: задачи-кандидаты, которые могут
войти в сценарии квартального планирования.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import BacklogItem, Issue, ScenarioAllocation
from app.repositories.base import BaseRepository
from app.services.backlog_service import BACKLOG_CATEGORY, BacklogService


router = APIRouter()


# === Schemas ===

class BacklogItemCreate(BaseModel):
    title: str
    project_id: Optional[str] = None
    quarter: Optional[str] = Field(default=None, max_length=10)
    year: Optional[int] = None
    priority: Optional[int] = None
    estimate_analyst_hours: Optional[float] = Field(default=None, ge=0)
    estimate_dev_hours: Optional[float] = Field(default=None, ge=0)
    estimate_qa_hours: Optional[float] = Field(default=None, ge=0)
    estimate_opo_hours: Optional[float] = Field(default=None, ge=0)
    opo_analyst_ratio: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    impact: Optional[str] = None
    risk: Optional[str] = None


class BacklogItemUpdate(BaseModel):
    title: Optional[str] = None
    project_id: Optional[str] = None
    quarter: Optional[str] = Field(default=None, max_length=10)
    year: Optional[int] = None
    priority: Optional[int] = None
    estimate_analyst_hours: Optional[float] = Field(default=None, ge=0)
    estimate_dev_hours: Optional[float] = Field(default=None, ge=0)
    estimate_qa_hours: Optional[float] = Field(default=None, ge=0)
    estimate_opo_hours: Optional[float] = Field(default=None, ge=0)
    opo_analyst_ratio: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    impact: Optional[str] = None
    risk: Optional[str] = None


class BacklogItemResponse(BaseModel):
    id: str
    title: str
    project_id: Optional[str] = None
    issue_id: Optional[str] = None
    jira_key: Optional[str] = None
    quarter: Optional[str] = None
    year: Optional[int] = None
    priority: Optional[int] = None
    estimate_hours: Optional[float] = None  # derived sum
    estimate_analyst_hours: Optional[float] = None
    estimate_dev_hours: Optional[float] = None
    estimate_qa_hours: Optional[float] = None
    estimate_opo_hours: Optional[float] = None
    opo_analyst_ratio: Optional[float] = None
    impact: Optional[str] = None
    risk: Optional[str] = None

    class Config:
        from_attributes = True


class LinkJiraRequest(BaseModel):
    jira_key: str


class RefreshResponse(BaseModel):
    created: int
    updated: int
    removed: int


# === Helpers ===

def _recompute_total(item: BacklogItem) -> None:
    """Пересчитать denormalized ``estimate_hours`` из per-role часов."""
    total = sum(
        v or 0
        for v in (
            item.estimate_analyst_hours,
            item.estimate_dev_hours,
            item.estimate_qa_hours,
            item.estimate_opo_hours,
        )
    )
    item.estimate_hours = total or None


def _to_response(item: BacklogItem) -> BacklogItemResponse:
    return BacklogItemResponse(
        id=item.id,
        title=item.title,
        project_id=item.project_id,
        issue_id=item.issue_id,
        jira_key=item.issue.key if item.issue else None,
        year=item.year,
        quarter=item.quarter,
        priority=item.priority,
        estimate_hours=item.estimate_hours,
        estimate_analyst_hours=item.estimate_analyst_hours,
        estimate_dev_hours=item.estimate_dev_hours,
        estimate_qa_hours=item.estimate_qa_hours,
        estimate_opo_hours=item.estimate_opo_hours,
        opo_analyst_ratio=item.opo_analyst_ratio,
        impact=item.impact,
        risk=item.risk,
    )


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
    query = db.query(BacklogItem).options(joinedload(BacklogItem.issue))
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
    return [_to_response(i) for i in items]


@router.post("", response_model=BacklogItemResponse, status_code=201)
async def create_backlog_item(
    data: BacklogItemCreate,
    db: Session = Depends(get_db),
):
    """Добавить элемент в бэклог."""
    repo = BaseRepository(BacklogItem, db)
    item = repo.create(data.model_dump())
    _recompute_total(item)
    db.commit()
    db.refresh(item)
    return _to_response(item)


@router.post("/refresh-from-jira", response_model=RefreshResponse)
async def refresh_from_jira(db: Session = Depends(get_db)):
    """Пробежать все Issue(category='initiatives_backlog') и синкнуть бэклог.

    Возвращает счётчики created / updated / removed.
    """
    svc = BacklogService(db)
    created = 0
    updated = 0

    existing_issue_ids = {
        i.issue_id
        for i in db.query(BacklogItem)
        .filter(BacklogItem.issue_id.isnot(None))
        .all()
    }

    # 1) Пройти по issues с backlog-категорией — create-or-update.
    issues = db.query(Issue).filter_by(category=BACKLOG_CATEGORY).all()
    for issue in issues:
        was = issue.id in existing_issue_ids
        svc.sync_from_issue(issue)
        if was:
            updated += 1
        else:
            created += 1

    # 2) Подчистить BacklogItem с issue_id, чей Issue больше не в backlog-категории.
    # Собираем stale list ДО итерации — sync может удалить запись, ломая итератор.
    stale = (
        db.query(BacklogItem)
        .options(joinedload(BacklogItem.issue))
        .join(Issue, BacklogItem.issue_id == Issue.id)
        .filter(Issue.category != BACKLOG_CATEGORY)
        .all()
    )
    removed = 0
    for item in stale:
        if item.issue is None:
            continue
        svc.sync_from_issue(item.issue)
        removed += 1

    db.commit()
    return RefreshResponse(created=created, updated=updated, removed=removed)


@router.get("/{item_id}", response_model=BacklogItemResponse)
async def get_backlog_item(
    item_id: str,
    db: Session = Depends(get_db),
):
    """Получить один элемент бэклога по id."""
    item = (
        db.query(BacklogItem)
        .options(joinedload(BacklogItem.issue))
        .filter(BacklogItem.id == item_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Backlog item not found")
    return _to_response(item)


@router.patch("/{item_id}", response_model=BacklogItemResponse)
async def update_backlog_item(
    item_id: str,
    data: BacklogItemUpdate,
    db: Session = Depends(get_db),
):
    """Частичное обновление элемента бэклога."""
    item = (
        db.query(BacklogItem)
        .options(joinedload(BacklogItem.issue))
        .filter(BacklogItem.id == item_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Backlog item not found")

    patch = data.model_dump(exclude_unset=True)
    if not patch:
        return _to_response(item)

    for key, value in patch.items():
        setattr(item, key, value)
    _recompute_total(item)
    db.commit()
    db.refresh(item)
    return _to_response(item)


@router.delete("/{item_id}")
async def delete_backlog_item(
    item_id: str,
    db: Session = Depends(get_db),
):
    """Удалить элемент бэклога.

    Если элемент уже используется в сохранённом сценарии планирования,
    возвращаем 409 — пусть пользователь сначала удалит сценарий.
    """
    repo = BaseRepository(BacklogItem, db)
    item = repo.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Backlog item not found")

    has_allocations = (
        db.query(ScenarioAllocation)
        .filter(ScenarioAllocation.backlog_item_id == item_id)
        .first()
        is not None
    )
    if has_allocations:
        raise HTTPException(
            status_code=409,
            detail=(
                "Backlog item is referenced by one or more planning scenarios; "
                "delete those scenarios first."
            ),
        )

    repo.delete(item)
    db.commit()
    return {"status": "deleted", "id": item_id}


@router.post("/{item_id}/link-jira", response_model=BacklogItemResponse)
async def link_jira(
    item_id: str,
    body: LinkJiraRequest,
    db: Session = Depends(get_db),
):
    """Привязать ручной BacklogItem к Jira-задаче.

    Перетягивает title / project_id / per-role estimates / impact / risk
    из Issue. Локальные ``priority`` / ``opo_analyst_ratio`` / ``year`` /
    ``quarter`` не трогаются.
    """
    item = (
        db.query(BacklogItem)
        .filter(BacklogItem.id == item_id)
        .first()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Backlog item not found")

    issue = db.query(Issue).filter_by(key=body.jira_key).first()
    if issue is None:
        raise HTTPException(
            status_code=404,
            detail=f"Issue {body.jira_key} not found locally — run sync first",
        )

    # Ensure one-to-one constraint not violated.
    other = (
        db.query(BacklogItem)
        .filter(BacklogItem.issue_id == issue.id, BacklogItem.id != item.id)
        .first()
    )
    if other is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Issue {body.jira_key} is already linked to another backlog item"
            ),
        )

    item.issue_id = issue.id
    # Pull estimates from issue (overwrite local values per spec).
    item.title = issue.summary
    item.project_id = issue.project_id
    item.estimate_analyst_hours = issue.planned_analyst_hours
    item.estimate_dev_hours = issue.planned_dev_hours
    item.estimate_qa_hours = issue.planned_qa_hours
    item.estimate_opo_hours = issue.planned_opo_hours
    item.impact = issue.impact
    item.risk = issue.risk
    _recompute_total(item)
    db.commit()
    # Reload with joined issue for response.
    item = (
        db.query(BacklogItem)
        .options(joinedload(BacklogItem.issue))
        .filter(BacklogItem.id == item_id)
        .first()
    )
    return _to_response(item)


@router.post("/{item_id}/unlink-jira", response_model=BacklogItemResponse)
async def unlink_jira(
    item_id: str,
    db: Session = Depends(get_db),
):
    """Сбросить связь BacklogItem с Jira-задачей.

    ``issue_id`` обнуляется, локальные оценки сохраняются — PM может
    допилить их вручную.
    """
    item = (
        db.query(BacklogItem)
        .filter(BacklogItem.id == item_id)
        .first()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Backlog item not found")

    item.issue_id = None
    db.commit()
    db.refresh(item)
    return _to_response(item)
