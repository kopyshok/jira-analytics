"""Issue configuration API — tree view, category assignment, analysis flags."""

import json
from collections import deque
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Issue, Project
from app.schemas.issue_context import (
    IssueChildNode,
    IssueContextAncestor,
    IssueContextChild,
    IssueContextResponse,
)
from app.services.backlog_service import BacklogService
from app.services.category_resolver import CategoryResolver
from app.services.event_bus import EventBroadcaster, get_event_bus
from app.services.hierarchy_rules import EvaluationInput, classify, load_rules

router = APIRouter()

# Коды категорий, которые автоматически исключают задачу из анализа.
# Используются для single/batch category endpoints.
ARCHIVE_CATEGORY_CODES = {"archive", "archive_target"}


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
    # Совпал ли узел с контейнерным правилом из hierarchy_rule. Такие
    # типы (Эпик, Main box и т.п.) являются родителями по определению —
    # категоризации не подлежат, UI блокирует Select.
    is_container: bool = False
    category_verified: bool = True
    require_child_verification: bool = False
    children: List["IssueTreeNode"] = []


class SetCategoryRequest(BaseModel):
    category_code: Optional[str] = None


class SetIncludeRequest(BaseModel):
    include: bool
    recursive: bool = False


class BatchCategoryRequest(BaseModel):
    issue_ids: List[str]
    category_code: Optional[str] = None


class VerifyRequest(BaseModel):
    cascade: bool = False
    require_child_verification: bool = False


class TreeCountsResponse(BaseModel):
    stack: int
    active: int
    initiatives: int
    archive_target: int
    archive: int


INITIATIVES_CODE = "initiatives_rfa"


def _filter_query_by_tree_params(query, project_keys, teams, db: Session):
    """Общий фильтр project_keys + teams (как в существующем /tree)."""
    query = query.join(Project, Issue.project_id == Project.id)
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
    return query


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

    # Правила иерархии нужны для классификации узлов на контейнерные
    # (родительские по типу — Эпик, Main box и т.п.) и прочие. Грузим один
    # раз, применяем к каждому issue.
    rules = load_rules(db)

    roots: list[IssueTreeNode] = []
    orphans: list[IssueTreeNode] = []
    node_map: dict[str, IssueTreeNode] = {}

    for issue in issues:
        project_key = project_key_by_id.get(issue.project_id, "")
        is_container_node = classify(rules, EvaluationInput(
            project_key=project_key,
            issue_type=issue.issue_type,
            has_parent=bool(issue.parent_id),
        ))
        node = IssueTreeNode(
            id=issue.id,
            key=issue.key,
            summary=issue.summary,
            issue_type=issue.issue_type,
            status=issue.status,
            status_category=issue.status_category,
            project_key=project_key,
            parent_key=by_id[issue.parent_id].key if issue.parent_id and issue.parent_id in by_id else None,
            assigned_category=issue.assigned_category,
            category=issue.category,
            include_in_analysis=issue.include_in_analysis if issue.include_in_analysis is not None else True,
            status_changed_at=issue.status_changed_at.isoformat() if issue.status_changed_at else None,
            goals=issue.goals or None,
            is_context=issue.id in context_ids,
            is_container=is_container_node,
            category_verified=issue.category_verified if issue.category_verified is not None else True,
            require_child_verification=issue.require_child_verification if issue.require_child_verification is not None else False,
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

    # Разделяем top-level: контейнеры (по правилам из hierarchy_rules) и всё,
    # что с детьми — остаются корнями; бездетные не-контейнеры (чистые
    # оперативные заявки без эпика) уходят в отдельную виртуальную группу.
    operations: list[IssueTreeNode] = []
    roots_keep: list[IssueTreeNode] = []
    for r in roots:
        if r.issue_type == "group":
            roots_keep.append(r)
            continue
        has_kids = bool(r.children)
        if not r.is_container and not has_kids and not r.is_context:
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


@router.get("/tree/counts", response_model=TreeCountsResponse)
def get_tree_counts(
    project_keys: Optional[str] = None,
    teams: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Счётчики по вкладкам категоризации. Не учитывает pending-правки клиента —
    клиент знает свои pending и сам корректирует UI; при «Сохранить» делает refetch.
    """
    base = _filter_query_by_tree_params(db.query(Issue), project_keys, teams, db)
    rows = base.all()

    # nodeById для walk up
    by_id = {r.id: r for r in rows}
    # Дотащим predков (вне scope) для walk up по inherited категории
    parent_ids_outside = {
        r.parent_id for r in rows
        if r.parent_id and r.parent_id not in by_id
    }
    if parent_ids_outside:
        # Подтянем предков до корня (без team-фильтра — нужны для inherited)
        ancestors = db.query(Issue).filter(Issue.id.in_(parent_ids_outside)).all()
        for a in ancestors:
            by_id[a.id] = a
        # Дотащить выше (parent of parent) — рекурсивно, но обычно 2-3 уровня
        frontier = {a.parent_id for a in ancestors if a.parent_id and a.parent_id not in by_id}
        while frontier:
            batch = db.query(Issue).filter(Issue.id.in_(frontier)).all()
            frontier = set()
            for a in batch:
                if a.id in by_id:
                    continue
                by_id[a.id] = a
                if a.parent_id and a.parent_id not in by_id:
                    frontier.add(a.parent_id)

    def effective(node: Issue) -> Optional[str]:
        if not (node.category_verified or False):
            return None
        if node.assigned_category:
            return node.assigned_category
        cur_id = node.parent_id
        for _ in range(20):
            if not cur_id:
                return None
            parent = by_id.get(cur_id)
            if not parent:
                return None
            if parent.assigned_category:
                return parent.assigned_category
            cur_id = parent.parent_id
        return None

    counts = {"stack": 0, "active": 0, "initiatives": 0, "archive_target": 0, "archive": 0}
    for r in rows:
        eff = effective(r)
        if eff is None:
            counts["stack"] += 1
        elif eff == INITIATIVES_CODE:
            counts["initiatives"] += 1
        elif eff == "archive_target":
            counts["archive_target"] += 1
        elif eff == "archive":
            counts["archive"] += 1
        else:
            counts["active"] += 1
    return TreeCountsResponse(**counts)


def _issue_is_container(db: Session, issue: Issue) -> bool:
    """True если issue совпал с контейнерным правилом (Эпик, Main box и т.п.).

    Флаг остаётся в ответе дерева для компоновки (контейнер без детей —
    всё равно корень, а не попадает в ``__operations__``), но категоризацию
    он больше не блокирует: пользователь может присвоить категорию эпику,
    и все потомки наследуют её через ``CategoryResolver`` (ancestor chain).
    """
    project = db.get(Project, issue.project_id) if issue.project_id else None
    project_key = project.key if project else ""
    return classify(load_rules(db), EvaluationInput(
        project_key=project_key,
        issue_type=issue.issue_type,
        has_parent=bool(issue.parent_id),
    ))


@router.put("/{issue_id}/category")
async def set_issue_category(
    issue_id: str,
    body: SetCategoryRequest,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    """Назначить категорию на задачу.

    Архивные категории (``archive``, ``archive_target``) дополнительно
    снимают ``include_in_analysis`` — такие задачи не участвуют в
    аналитике. Обратная операция (смена категории на не-архивную) флаг
    НЕ восстанавливает автоматически.

    Любая задача (включая контейнерные типы — Эпик, Main box, RFA-инициативы)
    может получить категорию напрямую: потомки наследуют её через
    ``CategoryResolver`` (walk up по ``parent_id``), так что один клик на
    эпике — и всё поддерево оказывается в целевой категории.
    """
    issue = db.get(Issue, issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    issue.assigned_category = body.category_code
    auto_excluded = False
    if body.category_code in ARCHIVE_CATEGORY_CODES and issue.include_in_analysis:
        issue.include_in_analysis = False
        auto_excluded = True

    # Пересчитать denormalized ``Issue.category`` — источник для
    # BacklogService.sync_from_issue. Повторяем логику MappingService для
    # одной задачи, чтобы не гонять весь пересчёт на каждое клик PM-а.
    resolver = CategoryResolver(db)
    issue.category = resolver.resolve_for_issue(issue).category_code

    # Auto-sync BacklogItem (create/update/delete) по эффективной
    # категории. Flush внутри сервиса, commit здесь.
    BacklogService(db).sync_from_issue(issue)

    # Snapshot attributes before commit — commit() expires them and a
    # subsequent access would trigger a reload on a potentially rotated
    # connection.
    key = issue.key
    assigned_category = issue.assigned_category
    include_in_analysis = issue.include_in_analysis
    db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["issues", "analytics"]})
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
    event_bus: EventBroadcaster = Depends(get_event_bus),
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
    await event_bus.publish({"type": "entity_changed", "entities": ["issues", "analytics"]})
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
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    """Пакетное назначение категории на несколько задач.

    При назначении любой архивной категории (``archive``, ``archive_target``)
    возвращает ``archived_ids`` — список задач, у которых одновременно
    снялся ``include_in_analysis``.

    Контейнерные задачи (Эпик, Main box, RFA-инициативы) больше не
    пропускаются: потомки унаследуют категорию через ``CategoryResolver``
    walk-up, так что установка категории на эпике = вся подветка уходит
    в ту же категорию.

    ``skipped_containers`` остаётся в ответе (всегда пустой) для обратной
    совместимости с фронтом.
    """
    updated = 0
    archived_ids: list[str] = []
    is_archive = body.category_code in ARCHIVE_CATEGORY_CODES
    resolver = CategoryResolver(db)
    backlog = BacklogService(db)
    for issue_id in body.issue_ids:
        issue = db.get(Issue, issue_id)
        if not issue:
            continue
        issue.assigned_category = body.category_code
        if is_archive and issue.include_in_analysis:
            issue.include_in_analysis = False
            archived_ids.append(issue.id)
        # Пересчитать denormalized category и синкнуть BacklogItem.
        issue.category = resolver.resolve_for_issue(issue).category_code
        backlog.sync_from_issue(issue)
        updated += 1
    db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["issues", "backlog"]})
    return {
        "ok": True,
        "updated": updated,
        "archived_ids": archived_ids,
        "skipped_containers": [],
    }


def _collect_unverified_descendants(db: Session, parent_id: str) -> list[Issue]:
    """BFS — все потомки с category_verified=False."""
    result: list[Issue] = []
    frontier = [parent_id]
    while frontier:
        children = db.query(Issue).filter(Issue.parent_id.in_(frontier)).all()
        frontier = []
        for ch in children:
            if not ch.category_verified:
                result.append(ch)
            frontier.append(ch.id)
    return result


@router.post("/{issue_id}/verify")
async def verify_issue(
    issue_id: str,
    body: VerifyRequest,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    """Подтвердить категорию задачи (переводит из «Стека к разбору» в нужную вкладку).

    cascade=True — рекурсивно подтверждает всех непроверенных потомков.
    require_child_verification сохраняется на задаче и управляет тем,
    попадут ли будущие новые дочерние задачи в стек автоматически.
    """
    issue = db.get(Issue, issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    verified_count = 0
    if not issue.category_verified:
        issue.category_verified = True
        verified_count += 1
    issue.require_child_verification = body.require_child_verification

    if body.cascade:
        for descendant in _collect_unverified_descendants(db, issue_id):
            descendant.category_verified = True
            verified_count += 1

    db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["issues"]})
    return {"ok": True, "verified_count": verified_count}


# ---------------------------------------------------------------------------
# Context endpoint
# ---------------------------------------------------------------------------

def _subtree_count(db: Session, root_id: str) -> int:
    """BFS вниз — считаем количество задач в поддереве (включая корень)."""
    count = 1
    frontier: deque[str] = deque([root_id])
    visited: set[str] = {root_id}
    while frontier:
        batch: list[str] = []
        while frontier:
            batch.append(frontier.popleft())
        children = (
            db.query(Issue.id)
            .filter(Issue.parent_id.in_(batch))
            .all()
        )
        for (child_id,) in children:
            if child_id not in visited:
                visited.add(child_id)
                frontier.append(child_id)
                count += 1
    return count


@router.get("/{issue_id}/context", response_model=IssueContextResponse)
def get_issue_context(
    issue_id: str,
    db: Session = Depends(get_db),
):
    """Контекст задачи: предки, дети, количество потомков, флаг контейнера."""
    issue = db.get(Issue, issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    rules = load_rules(db)

    # --- Ancestors (walk up parent_id, cycle guard max 20 steps) ---
    ancestors: list[IssueContextAncestor] = []
    seen_ids: set[str] = {issue.id}
    current = issue
    for _ in range(20):
        if not current.parent_id:
            break
        if current.parent_id in seen_ids:
            break  # cycle protection
        parent = db.get(Issue, current.parent_id)
        if not parent:
            break
        seen_ids.add(parent.id)
        ancestors.append(
            IssueContextAncestor(
                id=parent.id,
                key=parent.key,
                summary=parent.summary,
                issue_type=parent.issue_type,
            )
        )
        current = parent
    ancestors.reverse()  # от корня к родителю

    # --- Siblings total (children of direct parent) ---
    siblings_total = 0
    if issue.parent_id:
        siblings_total = (
            db.query(func.count(Issue.id))
            .filter(Issue.parent_id == issue.parent_id)
            .scalar()
        ) or 0

    # --- Direct children (up to 50) ---
    direct_children = (
        db.query(Issue)
        .filter(Issue.parent_id == issue.id)
        .limit(50)
        .all()
    )
    children_out: list[IssueContextChild] = []
    for ch in direct_children:
        children_out.append(
            IssueContextChild(
                id=ch.id,
                key=ch.key,
                summary=ch.summary,
                status=ch.status,
                status_category=ch.status_category,
                issue_type=ch.issue_type,
                category=ch.category,
                assigned_category=ch.assigned_category,
                include_in_analysis=ch.include_in_analysis if ch.include_in_analysis is not None else True,
                subtree_count=_subtree_count(db, ch.id),
            )
        )

    # --- is_container ---
    project = db.get(Project, issue.project_id) if issue.project_id else None
    project_key = project.key if project else ""
    is_container = classify(rules, EvaluationInput(
        project_key=project_key,
        issue_type=issue.issue_type,
        has_parent=bool(issue.parent_id),
    ))

    # --- subtree_count for root issue ---
    subtree_count = _subtree_count(db, issue.id)

    return IssueContextResponse(
        id=issue.id,
        key=issue.key,
        summary=issue.summary,
        status=issue.status,
        status_category=issue.status_category,
        issue_type=issue.issue_type,
        category=issue.category,
        assigned_category=issue.assigned_category,
        include_in_analysis=issue.include_in_analysis if issue.include_in_analysis is not None else True,
        is_container=is_container,
        ancestors=ancestors,
        siblings_total=siblings_total,
        children=children_out,
        subtree_count=subtree_count,
        description=issue.description,
        goals=issue.goals,
    )


@router.get("/{parent_id}/children", response_model=List[IssueChildNode])
def get_issue_children(
    parent_id: str,
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Прямые дети задачи (без рекурсии). Используется для popover соседей."""
    parent = db.get(Issue, parent_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    children = (
        db.query(Issue)
        .filter(Issue.parent_id == parent_id)
        .order_by(Issue.key)
        .limit(limit)
        .all()
    )
    return [
        IssueChildNode(
            id=ch.id,
            key=ch.key,
            summary=ch.summary,
            status=ch.status,
            status_category=ch.status_category,
            issue_type=ch.issue_type,
            category=ch.category,
            assigned_category=ch.assigned_category,
            include_in_analysis=ch.include_in_analysis if ch.include_in_analysis is not None else True,
        )
        for ch in children
    ]
