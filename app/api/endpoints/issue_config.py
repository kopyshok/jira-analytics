"""Issue configuration API — tree view, category assignment, analysis flags."""

import json
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Issue, Project

router = APIRouter()

ARCHIVE_CATEGORY_CODE = "archive"


# --- Schemas ---

class IssueTreeNode(BaseModel):
    id: str
    key: str
    summary: str
    issue_type: str
    status: str
    project_key: str
    parent_key: Optional[str] = None
    assigned_category: Optional[str] = None
    category: Optional[str] = None
    include_in_analysis: bool = True
    status_changed_at: Optional[str] = None
    children: List["IssueTreeNode"] = []


class SetCategoryRequest(BaseModel):
    category_code: Optional[str] = None


class SetIncludeRequest(BaseModel):
    include: bool
    recursive: bool = False


class BatchCategoryRequest(BaseModel):
    issue_ids: List[str]
    category_code: Optional[str] = None


# --- Endpoints ---

@router.get("/tree", response_model=List[IssueTreeNode])
async def get_issue_tree(
    project_keys: Optional[str] = None,
    teams: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Иерархическое дерево задач из БД.

    Фильтры:
    - project_keys — через запятую (PROJ1,PROJ2)
    - teams — через запятую (Team A,Team B); объединяется через OR.
      SQL-фильтр по ``Issue.team`` (продуктовая) ИЛИ
      ``Issue.participating_teams`` (JSON-массив).
    """
    query = db.query(Issue).join(Project, Issue.project_id == Project.id)

    if project_keys:
        scope_keys = [k.strip() for k in project_keys.split(",") if k.strip()]
        if scope_keys:
            query = query.filter(Project.key.in_(scope_keys))

    if teams:
        team_list = [t.strip() for t in teams.split(",") if t.strip()]
        if team_list:
            clauses = []
            for t in team_list:
                t_json = json.dumps(t, ensure_ascii=False)
                clauses.append(Issue.team == t)
                clauses.append(Issue.participating_teams.like(f"%{t_json}%"))
            query = query.filter(or_(*clauses))

    issues = query.all()

    # Build lookup
    by_id: dict[str, Issue] = {i.id: i for i in issues}
    by_key: dict[str, Issue] = {i.key: i for i in issues}

    # Build tree
    roots: list[IssueTreeNode] = []
    orphans: list[IssueTreeNode] = []
    node_map: dict[str, IssueTreeNode] = {}

    for issue in issues:
        node = IssueTreeNode(
            id=issue.id,
            key=issue.key,
            summary=issue.summary,
            issue_type=issue.issue_type,
            status=issue.status,
            project_key=db.get(Project, issue.project_id).key if issue.project_id else "",
            parent_key=by_id[issue.parent_id].key if issue.parent_id and issue.parent_id in by_id else None,
            assigned_category=issue.assigned_category,
            category=issue.category,
            include_in_analysis=issue.include_in_analysis if issue.include_in_analysis is not None else True,
            status_changed_at=issue.status_changed_at.isoformat() if issue.status_changed_at else None,
        )
        node_map[issue.id] = node

    for issue in issues:
        node = node_map[issue.id]
        if issue.parent_id and issue.parent_id in node_map:
            node_map[issue.parent_id].children.append(node)
        elif issue.parent_id and issue.parent_id not in node_map:
            # Parent exists but not in filtered set — orphan
            orphans.append(node)
        else:
            # No parent — top-level
            roots.append(node)

    # Add orphan group if any
    if orphans:
        orphan_group = IssueTreeNode(
            id="__orphans__",
            key="",
            summary="Без родителя",
            issue_type="group",
            status="",
            project_key="",
            children=orphans,
        )
        roots.insert(0, orphan_group)

    return roots


@router.put("/{issue_id}/category")
async def set_issue_category(
    issue_id: str,
    body: SetCategoryRequest,
    db: Session = Depends(get_db),
):
    """Назначить категорию на задачу.

    Категория ``archive`` дополнительно снимает ``include_in_analysis`` —
    архивные задачи не участвуют в аналитике. Обратная операция (смена
    категории с архива на другую) флаг НЕ восстанавливает автоматически.
    """
    issue = db.get(Issue, issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    issue.assigned_category = body.category_code
    auto_excluded = False
    if body.category_code == ARCHIVE_CATEGORY_CODE and issue.include_in_analysis:
        issue.include_in_analysis = False
        auto_excluded = True
    # Snapshot attributes before commit — commit() expires them and a
    # subsequent access would trigger a reload on a potentially rotated
    # connection.
    key = issue.key
    assigned_category = issue.assigned_category
    include_in_analysis = issue.include_in_analysis
    db.commit()
    return {
        "ok": True,
        "key": key,
        "assigned_category": assigned_category,
        "include_in_analysis": include_in_analysis,
        "auto_excluded": auto_excluded,
    }


@router.put("/{issue_id}/include")
async def set_issue_include(
    issue_id: str,
    body: SetIncludeRequest,
    db: Session = Depends(get_db),
):
    """Включить/исключить задачу из аналитики."""
    issue = db.get(Issue, issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    issue.include_in_analysis = body.include

    if body.recursive:
        _set_include_recursive(db, issue.id, body.include)

    key = issue.key
    include_in_analysis = issue.include_in_analysis
    db.commit()
    return {"ok": True, "key": key, "include_in_analysis": include_in_analysis}


def _set_include_recursive(db: Session, parent_id: str, include: bool) -> None:
    """Рекурсивно обновить include_in_analysis для всех потомков."""
    children = db.query(Issue).filter(Issue.parent_id == parent_id).all()
    for child in children:
        child.include_in_analysis = include
        _set_include_recursive(db, child.id, include)


@router.put("/batch-category")
async def batch_set_category(
    body: BatchCategoryRequest,
    db: Session = Depends(get_db),
):
    """Пакетное назначение категории на несколько задач.

    При назначении ``archive`` возвращает ``archived_ids`` — список задач,
    у которых одновременно снялся ``include_in_analysis``.
    """
    updated = 0
    archived_ids: list[str] = []
    is_archive = body.category_code == ARCHIVE_CATEGORY_CODE
    for issue_id in body.issue_ids:
        issue = db.get(Issue, issue_id)
        if issue:
            issue.assigned_category = body.category_code
            if is_archive and issue.include_in_analysis:
                issue.include_in_analysis = False
                archived_ids.append(issue.id)
            updated += 1
    db.commit()
    return {"ok": True, "updated": updated, "archived_ids": archived_ids}
