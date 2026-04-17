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

# Коды категорий, которые автоматически исключают задачу из анализа.
# Используются для single/batch category endpoints.
ARCHIVE_CATEGORY_CODES = {"archive", "archive_target"}

# Типы-контейнеры — могут иметь дочерние задачи. Всё остальное, что оказалось
# на верхнем уровне без детей (чистая оперативная заявка без эпика), уедет в
# виртуальную группу «Операционная работа (без эпика)» — чтобы дерево не
# расплывалось сотнями одиночных root-строк.
CONTAINER_ISSUE_TYPES = {
    "Эпик", "Epic",
    "Инициатива",
    "Инициатива (E-com)",
    "Инициатива (Ритейл)",
    "Инициатива (Финансы)",
    "История", "Story",
    "Цель",
}


# --- Schemas ---

class IssueTreeNode(BaseModel):
    id: str
    key: str
    summary: str
    issue_type: str
    status: str
    status_category: Optional[str] = None
    project_key: str
    parent_key: Optional[str] = None
    assigned_category: Optional[str] = None
    category: Optional[str] = None
    include_in_analysis: bool = True
    status_changed_at: Optional[str] = None
    goals: Optional[str] = None
    # True для задач-предков, дотащенных для контекста. Они не попали
    # под текущий фильтр (например, другая команда), но нужны чтобы
    # иерархия читалась. В UI такие строки показываются серыми, без
    # возможности править категорию или чекбокс.
    is_context: bool = False
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

    matched_issues = query.all()
    matched_ids = {i.id for i in matched_issues}

    # Дотащим предков, которые не попали под фильтр, чтобы иерархия была
    # читаемой. Такие задачи помечаются ``is_context=True`` — UI отключит
    # редактирование, но покажет их как якоря дерева.
    context_ids: set[str] = set()
    frontier: set[str] = {
        i.parent_id for i in matched_issues
        if i.parent_id and i.parent_id not in matched_ids
    }
    ancestors: list[Issue] = []
    while frontier:
        batch = db.query(Issue).filter(Issue.id.in_(frontier)).all()
        next_frontier: set[str] = set()
        for a in batch:
            if a.id in context_ids or a.id in matched_ids:
                continue
            context_ids.add(a.id)
            ancestors.append(a)
            if a.parent_id and a.parent_id not in matched_ids and a.parent_id not in context_ids:
                next_frontier.add(a.parent_id)
        frontier = next_frontier

    issues = list(matched_issues) + ancestors

    # Preload project keys once to avoid N+1 lookups.
    project_ids = {i.project_id for i in issues if i.project_id}
    projects = db.query(Project).filter(Project.id.in_(project_ids)).all() if project_ids else []
    project_key_by_id = {p.id: p.key for p in projects}

    by_id: dict[str, Issue] = {i.id: i for i in issues}

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
            status_category=issue.status_category,
            project_key=project_key_by_id.get(issue.project_id, ""),
            parent_key=by_id[issue.parent_id].key if issue.parent_id and issue.parent_id in by_id else None,
            assigned_category=issue.assigned_category,
            category=issue.category,
            include_in_analysis=issue.include_in_analysis if issue.include_in_analysis is not None else True,
            status_changed_at=issue.status_changed_at.isoformat() if issue.status_changed_at else None,
            goals=issue.goals or None,
            is_context=issue.id in context_ids,
        )
        node_map[issue.id] = node

    for issue in issues:
        node = node_map[issue.id]
        if issue.parent_id and issue.parent_id in node_map:
            node_map[issue.parent_id].children.append(node)
        elif issue.parent_id and issue.parent_id not in node_map:
            # Parent exists in DB but not returned (parent of ancestor we
            # chose not to climb further). Orphan group — rare edge case.
            orphans.append(node)
        else:
            roots.append(node)

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

    # Разделяем top-level: контейнеры (эпики/инициативы/истории) и всё,
    # что с детьми — остаются корнями; бездетные не-контейнеры (чистые
    # оперативные заявки без эпика) уходят в отдельную виртуальную группу.
    operations: list[IssueTreeNode] = []
    roots_keep: list[IssueTreeNode] = []
    for r in roots:
        if r.issue_type == "group":
            roots_keep.append(r)
            continue
        is_container = r.issue_type in CONTAINER_ISSUE_TYPES
        has_kids = bool(r.children)
        if not is_container and not has_kids and not r.is_context:
            operations.append(r)
        else:
            roots_keep.append(r)

    if operations:
        ops_group = IssueTreeNode(
            id="__operations__",
            key="",
            summary="Операционная работа (без эпика)",
            issue_type="group",
            status="",
            project_key="",
            children=operations,
        )
        roots_keep.append(ops_group)

    return roots_keep


@router.put("/{issue_id}/category")
async def set_issue_category(
    issue_id: str,
    body: SetCategoryRequest,
    db: Session = Depends(get_db),
):
    """Назначить категорию на задачу.

    Архивные категории (``archive``, ``archive_target``) дополнительно
    снимают ``include_in_analysis`` — такие задачи не участвуют в
    аналитике. Обратная операция (смена категории на не-архивную) флаг
    НЕ восстанавливает автоматически.
    """
    issue = db.get(Issue, issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    issue.assigned_category = body.category_code
    auto_excluded = False
    if body.category_code in ARCHIVE_CATEGORY_CODES and issue.include_in_analysis:
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

    При назначении любой архивной категории (``archive``, ``archive_target``)
    возвращает ``archived_ids`` — список задач, у которых одновременно
    снялся ``include_in_analysis``.
    """
    updated = 0
    archived_ids: list[str] = []
    is_archive = body.category_code in ARCHIVE_CATEGORY_CODES
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
