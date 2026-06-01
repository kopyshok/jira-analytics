"""Bulk-эндпоинты массового разбора задач (`/issues/bulk/*`).

Используются на странице «Категории задач» для PM-онбординга, когда в
стеке 1000+ задач и ручной разбор по дереву не масштабируется.
"""

import json
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Issue, Project

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
        )
        for r in rows
    ]
    return BulkPreviewResponse(
        total=total,
        truncated=total > body.limit,
        items=items,
    )
