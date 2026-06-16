"""Bulk-эндпоинты массового разбора задач (`/issues/bulk/*`).

Используются на странице «Категории задач» для PM-онбординга, когда в
стеке 1000+ задач и ручной разбор по дереву не масштабируется.
"""

import json
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Issue, Project
from app.services.backlog_service import BacklogService
from app.services.category_resolver import CategoryResolver
from app.services.event_bus import EventBroadcaster, get_event_bus

router = APIRouter()

ARCHIVE_CATEGORY_CODES = {"archive", "archive_target"}
MAX_BULK_LIMIT = 500


class BulkFilter(BaseModel):
    project_keys: Optional[List[str]] = None
    teams: Optional[List[str]] = None
    statuses: Optional[List[str]] = None
    status_changed_before: Optional[datetime] = None
    only_unverified: bool = False
    only_no_assigned: bool = False
    only_parent_changed: bool = False


class BulkPreviewRequest(BaseModel):
    filters: BulkFilter
    limit: int = Field(default=200, ge=1, le=MAX_BULK_LIMIT)


class BulkPreviewItem(BaseModel):
    id: str
    key: str
    summary: str
    status: str
    status_changed_at: Optional[str] = None
    category: Optional[str] = None
    assigned_category: Optional[str] = None
    project_key: str
    parent_changed: bool = False
    category_context: Optional[str] = None
    category_context_key: Optional[str] = None


class BulkPreviewResponse(BaseModel):
    total: int
    truncated: bool
    items: List[BulkPreviewItem]


def _apply_filters(query, filters: BulkFilter, db: Session):
    query = query.join(Project, Issue.project_id == Project.id)

    if filters.project_keys:
        query = query.filter(Project.key.in_(filters.project_keys))

    if filters.teams:
        clauses = []
        for t in filters.teams:
            t_json = json.dumps(t, ensure_ascii=False)
            clauses.append(Issue.team == t)
            clauses.append(Issue.participating_teams.like(f"%{t_json}%"))
        query = query.filter(or_(*clauses))

    if filters.statuses:
        query = query.filter(Issue.status.in_(filters.statuses))

    if filters.status_changed_before:
        cutoff = filters.status_changed_before
        if cutoff.tzinfo is not None:
            cutoff = cutoff.astimezone(timezone.utc).replace(tzinfo=None)
        query = query.filter(Issue.status_changed_at < cutoff)

    if filters.only_unverified:
        query = query.filter(Issue.category_verified.is_(False))

    if filters.only_no_assigned:
        query = query.filter(Issue.assigned_category.is_(None))

    if filters.only_parent_changed:
        query = query.filter(Issue.parent_changed.is_(True))

    return query


@router.post("/bulk/preview", response_model=BulkPreviewResponse)
def bulk_preview(
    body: BulkPreviewRequest,
    db: Session = Depends(get_db),
):
    """Превью задач, попадающих под фильтр. Без модификаций."""
    base = _apply_filters(db.query(Issue), body.filters, db)
    total = base.count()
    rows = base.order_by(Issue.key).limit(body.limit).all()

    project_ids = {r.project_id for r in rows if r.project_id}
    pkey_by_id = {
        p.id: p.key
        for p in db.query(Project).filter(Project.id.in_(project_ids)).all()
    } if project_ids else {}

    items = [
        BulkPreviewItem(
            id=r.id,
            key=r.key,
            summary=r.summary,
            status=r.status,
            status_changed_at=r.status_changed_at.isoformat() if r.status_changed_at else None,
            category=r.category,
            assigned_category=r.assigned_category,
            project_key=pkey_by_id.get(r.project_id, ""),
            parent_changed=bool(r.parent_changed),
            category_context=r.category_context,
            category_context_key=r.category_context_key,
        )
        for r in rows
    ]
    return BulkPreviewResponse(
        total=total,
        truncated=total > body.limit,
        items=items,
    )


class BulkArchiveRequest(BaseModel):
    filters: BulkFilter
    category_code: str


class BulkApplyResponse(BaseModel):
    updated: int
    archived_ids: List[str]


@router.post("/bulk/archive", response_model=BulkApplyResponse)
async def bulk_archive(
    body: BulkArchiveRequest,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    """Массовая архивация по фильтру.

    Принимает фильтр (как у preview) и архивный category_code. Применяет
    категорию ко всем матчащим задачам, снимает include_in_analysis.
    Запрещены не-архивные коды — для них используется существующий
    `/issues/batch-category` с явным списком id.
    """
    if body.category_code not in ARCHIVE_CATEGORY_CODES:
        raise HTTPException(
            status_code=400,
            detail="Можно выбрать только архивную категорию",
        )

    rows = _apply_filters(db.query(Issue), body.filters, db).all()
    resolver = CategoryResolver(db)
    backlog = BacklogService(db)
    archived_ids: list[str] = []
    for issue in rows:
        issue.assigned_category = body.category_code
        if issue.include_in_analysis:
            issue.include_in_analysis = False
            archived_ids.append(issue.id)
        issue.category = resolver.resolve_for_issue(issue).category_code
        backlog.sync_from_issue(issue)

    updated = len(rows)
    db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["issues", "backlog"]})
    return BulkApplyResponse(updated=updated, archived_ids=archived_ids)


class BulkAcceptSuggestionsRequest(BaseModel):
    filters: BulkFilter


class BulkAcceptResponse(BaseModel):
    applied: int
    skipped_no_suggestion: int


@router.post("/bulk/accept-suggestions", response_model=BulkAcceptResponse)
async def bulk_accept_suggestions(
    body: BulkAcceptSuggestionsRequest,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    """Перенести derived category (Issue.category) в assigned_category
    для задач без своей категории. Подтверждает (category_verified=True).

    Задачи без derived подсказки (Issue.category=NULL) пропускаются.
    """
    rows = _apply_filters(db.query(Issue), body.filters, db).all()
    backlog = BacklogService(db)
    applied = 0
    skipped = 0
    for issue in rows:
        if issue.assigned_category is not None:
            continue
        if not issue.category:
            skipped += 1
            continue
        issue.assigned_category = issue.category
        issue.category_verified = True
        if issue.category in ARCHIVE_CATEGORY_CODES and issue.include_in_analysis:
            issue.include_in_analysis = False
        backlog.sync_from_issue(issue)
        applied += 1

    db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["issues", "backlog"]})
    return BulkAcceptResponse(applied=applied, skipped_no_suggestion=skipped)


class BulkCascadeRequest(BaseModel):
    ancestor_ids: List[str]


class BulkCascadeResponse(BaseModel):
    applied: int
    skipped_ancestors: int


def _walk_subtree_no_assigned(db: Session, root_id: str) -> list[Issue]:
    """BFS вниз от root_id, останавливаемся на потомках с собственной
    assigned_category (граница). Сам root в результат не входит.
    """
    out: list[Issue] = []
    frontier = [root_id]
    visited: set[str] = {root_id}
    while frontier:
        children = db.query(Issue).filter(Issue.parent_id.in_(frontier)).all()
        next_frontier: list[str] = []
        for ch in children:
            if ch.id in visited:
                continue
            visited.add(ch.id)
            if ch.assigned_category is not None:
                # Граница каскада — ручной выбор PM. Поддерево под этой задачей
                # унаследует уже её код через CategoryResolver, не root'овый.
                continue
            out.append(ch)
            next_frontier.append(ch.id)
        frontier = next_frontier
    return out


@router.post("/bulk/cascade-inherit", response_model=BulkCascadeResponse)
async def bulk_cascade_inherit(
    body: BulkCascadeRequest,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    """Протолкнуть assigned_category эпика/контейнера на всех потомков
    без своей категории. Останавливается на ручных решениях PM.
    """
    ancestors = db.query(Issue).filter(Issue.id.in_(body.ancestor_ids)).all()
    backlog = BacklogService(db)
    applied = 0
    skipped_ancestors = 0
    for anc in ancestors:
        if not anc.assigned_category:
            skipped_ancestors += 1
            continue
        descendants = _walk_subtree_no_assigned(db, anc.id)
        for d in descendants:
            d.assigned_category = anc.assigned_category
            d.category = anc.assigned_category
            d.category_verified = True
            if anc.assigned_category in ARCHIVE_CATEGORY_CODES and d.include_in_analysis:
                d.include_in_analysis = False
            backlog.sync_from_issue(d)
            applied += 1

    db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["issues", "backlog"]})
    return BulkCascadeResponse(applied=applied, skipped_ancestors=skipped_ancestors)
