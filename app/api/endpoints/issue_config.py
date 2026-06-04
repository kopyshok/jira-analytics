"""Issue configuration API — tree view, category assignment, analysis flags."""

import json
from collections import deque
from typing import Optional, List, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Issue, Project, PlanAudit
from app.schemas.issue_context import (
    IssueContextAncestor,
    IssueContextChild,
    IssueContextResponse,
)
from app.services.backlog_service import BacklogService
from app.services.category_resolver import CategoryResolver
from app.services.event_bus import EventBroadcaster, get_event_bus
from app.services.hierarchy_rules import EvaluationInput, classify, load_rules
from app.services.hours_breakdown_service import HoursBreakdownService
from app.services.plan_edit_service import PlanEditService, ROLES as PLAN_ROLES
from app.core.auth_deps import get_current_user

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
    verify: bool = False


class VerifyRequest(BaseModel):
    cascade: bool = False
    require_child_verification: bool = False
    category_code: Optional[str] = None
    has_category_code: bool = False


class TreeCountsResponse(BaseModel):
    stack: int
    active: int
    initiatives: int
    archive_target: int
    archive: int


class IssueTreeRootNode(BaseModel):
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
    is_context: bool = False
    is_container: bool = False
    category_verified: bool = True
    require_child_verification: bool = False
    has_children: bool = False
    descendant_count: int = 0
    descendant_match_count: int = 0


INITIATIVES_CODE = "initiatives_rfa"


def _filter_query_by_tree_params(query, project_keys, teams, db: Session, primary_only: bool = False):
    """Общий фильтр project_keys + teams.

    ``primary_only=False`` (default): задача включается если её ``team`` совпадает
    ИЛИ команда упомянута в ``participating_teams`` (используется legacy /tree
    и bulk endpoints — там participating важен).

    ``primary_only=True``: только продуктовая команда (``Issue.team``).
    Используется на /categories (lazy endpoints) — категоризация отвечает
    продуктовая команда; participating-задачи разбирает чужой PM.
    """
    query = query.join(Project, Issue.project_id == Project.id)
    if project_keys:
        scope_keys = [k.strip() for k in project_keys.split(",") if k.strip()]
        if scope_keys:
            query = query.filter(Project.key.in_(scope_keys))
    if teams:
        team_list = [t.strip() for t in teams.split(",") if t.strip()]
        if team_list:
            if primary_only:
                query = query.filter(Issue.team.in_(team_list))
            else:
                clauses = []
                for t in team_list:
                    t_json = json.dumps(t, ensure_ascii=False)
                    clauses.append(Issue.team == t)
                    clauses.append(Issue.participating_teams.like(f"%{t_json}%"))
                query = query.filter(or_(*clauses))
    return query


def _node_matches_tab(effective_code: Optional[str], verified: bool, tab: str) -> bool:
    """Проверить, совпадает ли узел с фильтром вкладки."""
    if not verified:
        return tab == "stack"
    if tab == "stack":
        return effective_code is None
    if tab == "active":
        return (effective_code is not None
                and effective_code not in ARCHIVE_CATEGORY_CODES
                and effective_code != INITIATIVES_CODE)
    if tab == "initiatives":
        return effective_code == INITIATIVES_CODE
    if tab == "archive_target":
        return effective_code == "archive_target"
    if tab == "archive":
        return effective_code == "archive"
    return False


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


def _load_context_ancestors(
    db: Session, matched_ids: set[str], matched_by_id: dict[str, Issue]
) -> dict[str, Issue]:
    """Дотащить предков, не попавших под фильтр команды.

    Для каждой matched-задачи с ``parent_id`` вне ``matched_ids`` поднимаемся
    по цепочке до корня (или до встречи с уже известным узлом). Возвращает
    словарь ``id -> Issue`` контекстных предков. UI рендерит их как
    read-only якоря дерева (``is_context=True``).
    """
    context: dict[str, Issue] = {}
    frontier: set[str] = {
        i.parent_id for i in matched_by_id.values()
        if i.parent_id and i.parent_id not in matched_ids
    }
    while frontier:
        batch = db.query(Issue).filter(Issue.id.in_(frontier)).all()
        next_frontier: set[str] = set()
        for a in batch:
            if a.id in context or a.id in matched_ids:
                continue
            context[a.id] = a
            if a.parent_id and a.parent_id not in matched_ids and a.parent_id not in context:
                next_frontier.add(a.parent_id)
        frontier = next_frontier
    return context


@router.get("/tree/counts", response_model=TreeCountsResponse)
def get_tree_counts(
    project_keys: Optional[str] = None,
    teams: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Счётчики по вкладкам категоризации. Не учитывает pending-правки клиента —
    клиент знает свои pending и сам корректирует UI; при «Сохранить» делает refetch.

    ``primary_only=True`` — участвующие задачи (participating_teams) не считаются.
    Чужие предки (in-team задача под чужим эпиком) подтягиваются в
    ``by_id_full`` для корректного walk-up через ``CategoryResolver``, но
    САМИ В СЧЁТЧИКИ НЕ ИДУТ — считаются только продуктовые задачи команды.
    """
    base = _filter_query_by_tree_params(db.query(Issue), project_keys, teams, db, primary_only=True)
    rows = base.all()
    by_id = {r.id: r for r in rows}
    # Чужие предки нужны только для разрешения эффективной категории.
    context_ancestors = _load_context_ancestors(db, set(by_id.keys()), by_id)
    by_id_full = {**by_id, **context_ancestors}

    def effective(node: Issue) -> Optional[str]:
        if not (node.category_verified or False):
            return None
        if node.assigned_category:
            return node.assigned_category
        cur_id = node.parent_id
        for _ in range(20):
            if not cur_id:
                return None
            parent = by_id_full.get(cur_id)
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


@router.get("/tree/roots", response_model=List[IssueTreeRootNode])
def get_tree_roots(
    project_keys: Optional[str] = None,
    teams: Optional[str] = None,
    tab: str = "stack",
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Корневые узлы вкладки. «Корень» = верхнеуровневая задача (или эпик),
    которая сама матчит вкладку ИЛИ содержит матчащих потомков. Поиск
    применяется к key + summary (LIKE %q%).

    ``primary_only=True`` — participating-задачи не подтягиваются.

    Чужие предки (in-team задача под чужим эпиком) показываются как
    read-only якоря дерева с ``is_context=True``: PM видит контекст
    (под каким эпиком висит задача), но править эпик не может —
    он принадлежит другой команде.
    """
    base = _filter_query_by_tree_params(db.query(Issue), project_keys, teams, db, primary_only=True)
    matched_rows = base.all()
    matched_by_id: dict[str, Issue] = {r.id: r for r in matched_rows}

    # Дотащить чужих предков как read-only контекст.
    context_ancestors = _load_context_ancestors(db, set(matched_by_id.keys()), matched_by_id)
    context_ids: set[str] = set(context_ancestors.keys())
    by_id: dict[str, Issue] = {**matched_by_id, **context_ancestors}

    project_key_by_id = {
        p.id: p.key
        for p in db.query(Project)
        .filter(Project.id.in_({r.project_id for r in by_id.values() if r.project_id}))
        .all()
    }

    rules = load_rules(db)

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

    search_lc = (search or "").strip().lower()
    # Если строка поиска похожа на полный Jira-ключ (PROJ-123) — сравниваем
    # ключи строго равенством. Иначе "ITL-57" подматчит и "ITL-571",
    # "ITL-579" и т.п. — слишком шумно для PM.
    import re as _re
    key_search = bool(_re.fullmatch(r"[a-z][a-z0-9]*-\d+", search_lc))

    def text_matches(node: Issue) -> bool:
        if not search_lc:
            return True
        if key_search:
            return (node.key or "").lower() == search_lc
        return search_lc in (node.key or "").lower() or search_lc in (node.summary or "").lower()

    self_match: dict[str, bool] = {}
    for r in by_id.values():
        if r.id in context_ids:
            # Чужой предок никогда не считается self-match: он не относится
            # к команде PM-а и не должен раздувать счётчики дочерних веток.
            self_match[r.id] = False
            continue
        self_match[r.id] = (
            _node_matches_tab(effective(r), r.category_verified or False, tab)
            and text_matches(r)
        )

    children_by_parent: dict[str, list[Issue]] = {}
    for r in by_id.values():
        if r.parent_id:
            children_by_parent.setdefault(r.parent_id, []).append(r)

    desc_total: dict[str, int] = {}
    desc_match: dict[str, int] = {}
    def compute_desc(node_id: str) -> tuple[int, int]:
        if node_id in desc_total:
            return desc_total[node_id], desc_match[node_id]
        t = 0
        m = 0
        for ch in children_by_parent.get(node_id, []):
            t += 1
            if self_match.get(ch.id):
                m += 1
            ct, cm = compute_desc(ch.id)
            t += ct
            m += cm
        desc_total[node_id] = t
        desc_match[node_id] = m
        return t, m

    for r in by_id.values():
        compute_desc(r.id)

    roots: list[IssueTreeRootNode] = []
    for r in by_id.values():
        is_top = (not r.parent_id) or (r.parent_id not in by_id)
        if not is_top:
            continue
        node_self_match = self_match.get(r.id, False)
        if not node_self_match and desc_match.get(r.id, 0) == 0:
            continue
        is_container = classify(rules, EvaluationInput(
            project_key=project_key_by_id.get(r.project_id, ""),
            issue_type=r.issue_type,
            has_parent=bool(r.parent_id),
        ))
        # tab context: root попал из-за совпавшего потомка, сам не матчит.
        # Помечаем is_context=true → фронт рендерит как read-only.
        is_tab_context = (not node_self_match) or (r.id in context_ids)
        roots.append(IssueTreeRootNode(
            id=r.id,
            key=r.key,
            summary=r.summary,
            issue_type=r.issue_type,
            status=r.status,
            status_category=r.status_category,
            project_key=project_key_by_id.get(r.project_id, ""),
            parent_key=by_id[r.parent_id].key if r.parent_id and r.parent_id in by_id else None,
            assigned_category=r.assigned_category,
            category=r.category,
            include_in_analysis=r.include_in_analysis if r.include_in_analysis is not None else True,
            status_changed_at=r.status_changed_at.isoformat() if r.status_changed_at else None,
            goals=r.goals or None,
            is_context=is_tab_context,
            is_container=is_container,
            category_verified=r.category_verified if r.category_verified is not None else True,
            require_child_verification=r.require_child_verification if r.require_child_verification is not None else False,
            has_children=bool(children_by_parent.get(r.id)),
            descendant_count=desc_total.get(r.id, 0),
            descendant_match_count=desc_match.get(r.id, 0),
        ))

    roots.sort(key=lambda n: n.key)
    return roots


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
        if body.verify:
            issue.category_verified = True
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

    resolver = CategoryResolver(db)
    backlog = BacklogService(db)
    apply_code = body.has_category_code
    is_archive = apply_code and body.category_code in ARCHIVE_CATEGORY_CODES

    if apply_code:
        issue.assigned_category = body.category_code
        if is_archive and issue.include_in_analysis:
            issue.include_in_analysis = False
        issue.category = resolver.resolve_for_issue(issue).category_code
        backlog.sync_from_issue(issue)

    verified_count = 0
    if not issue.category_verified:
        issue.category_verified = True
        verified_count += 1
    issue.require_child_verification = body.require_child_verification

    if body.cascade:
        for descendant in _collect_unverified_descendants(db, issue_id):
            if apply_code:
                descendant.assigned_category = body.category_code
                if is_archive and descendant.include_in_analysis:
                    descendant.include_in_analysis = False
                descendant.category = resolver.resolve_for_issue(descendant).category_code
                backlog.sync_from_issue(descendant)
            descendant.category_verified = True
            verified_count += 1

    db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["issues", "backlog"]})
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


@router.get("/{issue_id}/hours-breakdown")
def get_hours_breakdown(
    issue_id: str,
    year: int = Query(..., ge=2000, le=2100),
    quarter: int = Query(..., ge=1, le=4),
    db: Session = Depends(get_db),
):
    """6 колонок часов для длинной RFA.

    См. spec: docs/superpowers/specs/2026-06-03-rfa-epic-hierarchy-design.md
    """
    issue = db.query(Issue).filter(Issue.id == issue_id).one_or_none()
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    return HoursBreakdownService(db).calculate(issue_id, year, quarter)


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


class EpicCandidateSchema(BaseModel):
    id: str
    key: str
    summary: str
    assigned_category: str


@router.get("/tree/epic-candidates", response_model=List[EpicCandidateSchema])
def get_epic_candidates(
    project_keys: Optional[str] = None,
    teams: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Задачи с assigned_category и хотя бы одним ребёнком — кандидаты на каскад
    в bulk-drawer. Фильтр scope/teams тот же, что у tree/roots (primary_only).
    """
    base = _filter_query_by_tree_params(db.query(Issue), project_keys, teams, db, primary_only=True)
    base = base.filter(Issue.assigned_category.isnot(None))
    candidates = base.all()
    # has_children check
    ids_with_kids = {
        cid for (cid,) in db.query(Issue.parent_id)
        .filter(Issue.parent_id.in_({c.id for c in candidates}))
        .distinct().all()
    }
    return [
        EpicCandidateSchema(
            id=c.id, key=c.key, summary=c.summary,
            assigned_category=c.assigned_category,
        )
        for c in candidates if c.id in ids_with_kids
    ]


class PlanEditRequest(BaseModel):
    role_hours: Dict[str, Optional[float]]
    comment: str = Field(..., min_length=1)


class PlanRevertRequest(BaseModel):
    audit_id: Optional[str] = None


@router.patch("/{issue_id}/plan")
def patch_plan(
    issue_id: str,
    payload: PlanEditRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    issue = db.query(Issue).filter_by(id=issue_id).one_or_none()
    if issue is None:
        raise HTTPException(404, "Issue not found")
    try:
        PlanEditService(db).edit(
            issue_id, payload.role_hours, payload.comment,
            user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))
    db.refresh(issue)
    return {
        "plan": {r: getattr(issue, f"planned_{r}_hours") for r in PLAN_ROLES}
    }


@router.post("/{issue_id}/plan/revert")
def revert_plan(
    issue_id: str,
    payload: PlanRevertRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    issue = db.query(Issue).filter_by(id=issue_id).one_or_none()
    if issue is None:
        raise HTTPException(404, "Issue not found")
    PlanEditService(db).revert(
        issue_id, audit_id=payload.audit_id,
        user_id=current_user.id,
    )
    db.refresh(issue)
    return {
        "plan": {r: getattr(issue, f"planned_{r}_hours") for r in PLAN_ROLES}
    }


class ConflictResolveRequest(BaseModel):
    action: str  # 'accept_jira' | 'ignore'
    role: str


@router.post("/{issue_id}/plan/conflict-resolve")
def resolve_plan_conflict(
    issue_id: str,
    payload: ConflictResolveRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    issue = db.query(Issue).filter_by(id=issue_id).one_or_none()
    if issue is None:
        raise HTTPException(404, "Issue not found")
    try:
        PlanEditService(db).resolve_conflict(
            issue_id, payload.role, payload.action,
            user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"ok": True}


@router.get("/{issue_id}/plan-conflicts")
def get_plan_conflicts(issue_id: str, db: Session = Depends(get_db)):
    issue = db.query(Issue).filter_by(id=issue_id).one_or_none()
    if issue is None:
        raise HTTPException(404, "Issue not found")
    return PlanEditService(db).open_conflicts(issue_id)


@router.get("/{issue_id}/plan-history")
def plan_history(issue_id: str, db: Session = Depends(get_db)):
    issue = db.query(Issue).filter_by(id=issue_id).one_or_none()
    if issue is None:
        raise HTTPException(404, "Issue not found")
    rows = PlanEditService(db).history(issue_id)
    return [
        {
            "id": r.id, "role": r.role,
            "value_before": r.value_before, "value_after": r.value_after,
            "source": r.source, "user_id": r.user_id, "comment": r.comment,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/{parent_id}/children", response_model=List[IssueTreeRootNode])
def get_issue_children(
    parent_id: str,
    tab: Optional[str] = None,
    teams: Optional[str] = None,
    project_keys: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Прямые + транзитивные дети, отфильтрованные по вкладке (если задана).

    Без `tab` — только прямые дети (обратная совместимость с popover-соседями).
    С `tab` — все потомки на любой глубине, матчащие вкладку.

    Если задан `teams` — применяется тот же ``primary_only=True`` фильтр,
    что и на /tree/roots: чужие дети с in-team потомками возвращаются как
    read-only контекст (``is_context=True``); чужие дети без in-team
    потомков скрыты полностью.
    """
    parent = db.get(Issue, parent_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    rules = load_rules(db)

    team_list = [t.strip() for t in (teams or "").split(",") if t.strip()] if teams else []
    project_key_list = [k.strip() for k in (project_keys or "").split(",") if k.strip()] if project_keys else []

    def in_team(issue: Issue, proj_key: str) -> bool:
        """Совпадает ли задача с фильтром (по команде и/или scope-проекту)."""
        if project_key_list and proj_key not in project_key_list:
            return False
        if team_list and (issue.team or "") not in team_list:
            return False
        return True

    if not tab:
        # Backward compatibility: прямые дети без фильтра
        children = (
            db.query(Issue)
            .filter(Issue.parent_id == parent_id)
            .order_by(Issue.key)
            .limit(limit)
            .all()
        )
        proj_keys_map = {
            p.id: p.key
            for p in db.query(Project).filter(Project.id.in_({c.project_id for c in children if c.project_id})).all()
        }
        if team_list or project_key_list:
            children = [ch for ch in children if in_team(ch, proj_keys_map.get(ch.project_id, ""))]
        has_kids_set = {
            cid for (cid,) in db.query(Issue.parent_id)
            .filter(Issue.parent_id.in_({c.id for c in children}))
            .distinct().all()
        }
        return [
            IssueTreeRootNode(
                id=ch.id,
                key=ch.key,
                summary=ch.summary,
                issue_type=ch.issue_type,
                status=ch.status,
                status_category=ch.status_category,
                project_key=proj_keys_map.get(ch.project_id, ""),
                parent_key=parent.key,
                assigned_category=ch.assigned_category,
                category=ch.category,
                include_in_analysis=ch.include_in_analysis if ch.include_in_analysis is not None else True,
                status_changed_at=ch.status_changed_at.isoformat() if ch.status_changed_at else None,
                goals=ch.goals or None,
                is_context=False,
                is_container=classify(rules, EvaluationInput(
                    project_key=proj_keys_map.get(ch.project_id, ""),
                    issue_type=ch.issue_type,
                    has_parent=True,
                )),
                category_verified=ch.category_verified if ch.category_verified is not None else True,
                require_child_verification=ch.require_child_verification if ch.require_child_verification is not None else False,
                has_children=ch.id in has_kids_set,
                descendant_count=0,
                descendant_match_count=0,
            )
            for ch in children
        ]

    # С tab: возвращаем ПРЯМЫЕ дети parent_id, которые либо сами матчат вкладку,
    # либо имеют tab-матчащих потомков глубже. Иерархия сохраняется — PM
    # раскрывает intermediate уровни поэтапно. Внуки НЕ всплывают в плоский
    # список (иначе дубликаты при раскрытии разных уровней).
    direct_children = (
        db.query(Issue).filter(Issue.parent_id == parent_id).all()
    )
    if not direct_children:
        return []

    # Полное поддерево для подсчёта desc_match по каждому прямому ребёнку
    subtree: dict[str, Issue] = {c.id: c for c in direct_children}
    frontier = [c.id for c in direct_children]
    while frontier:
        batch = db.query(Issue).filter(Issue.parent_id.in_(frontier)).limit(limit * 10).all()
        next_f = []
        for d in batch:
            if d.id in subtree:
                continue
            subtree[d.id] = d
            next_f.append(d.id)
        frontier = next_f

    by_id_full = dict(subtree)
    by_id_full[parent.id] = parent
    cur = parent
    while cur.parent_id and cur.parent_id not in by_id_full:
        anc = db.get(Issue, cur.parent_id)
        if not anc:
            break
        by_id_full[anc.id] = anc
        cur = anc

    def effective(node: Issue) -> Optional[str]:
        if not (node.category_verified or False):
            return None
        if node.assigned_category:
            return node.assigned_category
        cur_id = node.parent_id
        for _ in range(20):
            if not cur_id:
                return None
            par = by_id_full.get(cur_id)
            if not par:
                return None
            if par.assigned_category:
                return par.assigned_category
            cur_id = par.parent_id
        return None

    # Карта project_key для всего subtree (нужна и для in_team, и для ответа).
    proj_keys_map = {
        p.id: p.key
        for p in db.query(Project)
        .filter(Project.id.in_({c.project_id for c in subtree.values() if c.project_id}))
        .all()
    }

    def node_in_team(node: Issue) -> bool:
        # Если фильтр не задан — все «свои».
        if not team_list and not project_key_list:
            return True
        return in_team(node, proj_keys_map.get(node.project_id, ""))

    def matches_tab(node: Issue) -> bool:
        return _node_matches_tab(effective(node), node.category_verified or False, tab)

    search_lc = (search or "").strip().lower()
    import re as _re
    key_search = bool(_re.fullmatch(r"[a-z][a-z0-9]*-\d+", search_lc))

    def text_matches(node: Issue) -> bool:
        if not search_lc:
            return True
        if key_search:
            return (node.key or "").lower() == search_lc
        return search_lc in (node.key or "").lower() or search_lc in (node.summary or "").lower()

    def in_team_match(node: Issue) -> bool:
        # Чужой узел никогда не считается self-match: он не категоризуется
        # для текущего PM и не должен раздувать счётчики. Поиск тоже учитывается:
        # под раскрытым контекст-предком должны быть видны ТОЛЬКО задачи,
        # которые совпали с поисковой строкой (или их прямые предки).
        return node_in_team(node) and matches_tab(node) and text_matches(node)

    # BFS desc_match для каждого узла в subtree (in-team matched only)
    children_by_parent: dict[str, list[Issue]] = {}
    for d in subtree.values():
        if d.parent_id:
            children_by_parent.setdefault(d.parent_id, []).append(d)

    desc_match_cache: dict[str, int] = {}
    def desc_match(node_id: str) -> int:
        if node_id in desc_match_cache:
            return desc_match_cache[node_id]
        total = 0
        for ch in children_by_parent.get(node_id, []):
            if in_team_match(ch):
                total += 1
            total += desc_match(ch.id)
        desc_match_cache[node_id] = total
        return total

    matched = [
        c for c in direct_children
        if in_team_match(c) or desc_match(c.id) > 0
    ]
    matched.sort(key=lambda c: c.key)
    matched = matched[:limit]

    has_kids_set = {c.id for c in matched if children_by_parent.get(c.id)}
    return [
        IssueTreeRootNode(
            id=ch.id,
            key=ch.key,
            summary=ch.summary,
            issue_type=ch.issue_type,
            status=ch.status,
            status_category=ch.status_category,
            project_key=proj_keys_map.get(ch.project_id, ""),
            parent_key=by_id_full[ch.parent_id].key if ch.parent_id in by_id_full else None,
            assigned_category=ch.assigned_category,
            category=ch.category,
            include_in_analysis=ch.include_in_analysis if ch.include_in_analysis is not None else True,
            status_changed_at=ch.status_changed_at.isoformat() if ch.status_changed_at else None,
            goals=ch.goals or None,
            # is_context=True если узел чужой (foreign-team якорь), ИЛИ свой,
            # но сам не матчит вкладку / поиск (попал как мост к совпавшим
            # потомкам). UI рендерит как read-only.
            is_context=(not node_in_team(ch)) or (not matches_tab(ch)) or (not text_matches(ch)),
            is_container=classify(rules, EvaluationInput(
                project_key=proj_keys_map.get(ch.project_id, ""),
                issue_type=ch.issue_type,
                has_parent=bool(ch.parent_id),
            )),
            category_verified=ch.category_verified if ch.category_verified is not None else True,
            require_child_verification=ch.require_child_verification if ch.require_child_verification is not None else False,
            has_children=ch.id in has_kids_set,
            descendant_count=0,
            descendant_match_count=desc_match(ch.id),
        )
        for ch in matched
    ]
