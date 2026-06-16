"""Backlog items API endpoints.

Пул задач-инициатив (категория «Инициативы и RFA»). Квартальной привязки
у элементов нет — квартал выбирается в сценарии планирования.
"""

import asyncio
import json
from contextlib import suppress
from datetime import datetime
from typing import Awaitable, Callable, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, aliased, joinedload

from app.connectors.jira_client import JiraClient, JiraClientError
from app.database import get_db
from app.models import AppSetting, BacklogItem, Employee, Issue, PlanningScenario, ScenarioAllocation
from app.repositories.base import BaseRepository
from app.services.backlog_service import (
    BACKLOG_CATEGORY,
    QUARTERLY_TASKS_CATEGORY,
    TRACKED_CATEGORIES,
    BacklogService,
    is_cancel_like,
    mode_excluded_backlog_ids,
)
from app.services.category_resolver import CategoryResolver
from app.services.event_bus import EventBroadcaster, get_event_bus
from app.services.hierarchy_rules import is_explicit_leaf, load_rules
from app.services.sync_service import SyncService


router = APIRouter()


# === Schemas ===

class BacklogItemCreate(BaseModel):
    title: str
    project_id: Optional[str] = None
    team: Optional[str] = None
    priority: Optional[int] = None
    estimate_analyst_hours: Optional[float] = Field(default=None, ge=0)
    estimate_dev_hours: Optional[float] = Field(default=None, ge=0)
    estimate_qa_hours: Optional[float] = Field(default=None, ge=0)
    estimate_opo_hours: Optional[float] = Field(default=None, ge=0)
    opo_analyst_ratio: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    impact: Optional[str] = None
    risk: Optional[str] = None
    parallel_count_analyst: Optional[int] = Field(default=None, ge=1, le=5)
    parallel_count_dev: Optional[int] = Field(default=None, ge=1, le=5)
    parallel_count_qa: Optional[int] = Field(default=None, ge=1, le=5)


class BacklogItemUpdate(BaseModel):
    title: Optional[str] = None
    project_id: Optional[str] = None
    team: Optional[str] = None
    priority: Optional[int] = Field(default=None, ge=1, le=10)
    estimate_analyst_hours: Optional[float] = Field(default=None, ge=0)
    estimate_dev_hours: Optional[float] = Field(default=None, ge=0)
    estimate_qa_hours: Optional[float] = Field(default=None, ge=0)
    estimate_opo_hours: Optional[float] = Field(default=None, ge=0)
    opo_analyst_ratio: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    impact: Optional[str] = None
    risk: Optional[str] = None
    parallel_count_analyst: Optional[int] = Field(default=None, ge=1, le=5)
    parallel_count_dev: Optional[int] = Field(default=None, ge=1, le=5)
    parallel_count_qa: Optional[int] = Field(default=None, ge=1, le=5)
    involvement_analyst: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    involvement_dev: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    involvement_qa: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    involvement_launch: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    duration_analyst_days: Optional[float] = Field(default=None, ge=0)
    duration_dev_days: Optional[float] = Field(default=None, ge=0)
    duration_qa_days: Optional[float] = Field(default=None, ge=0)
    duration_launch_days: Optional[float] = Field(default=None, ge=0)


class ScenarioRef(BaseModel):
    id: str
    name: str


class BacklogChildSchema(BaseModel):
    id: str              # backlog_item.id (нужен для PATCH /included)
    issue_id: str
    key: str
    title: str
    issue_type: Optional[str] = None
    status: Optional[str] = None
    included_in_planning: bool = True
    # Плановые часы дочернего Эпика — чтобы строка-ребёнок в таблице показывала
    # свои АН/ПР/ТС/ОПЭ, а не нули.
    estimate_hours: Optional[float] = None
    estimate_analyst_hours: Optional[float] = None
    estimate_dev_hours: Optional[float] = None
    estimate_qa_hours: Optional[float] = None
    estimate_opo_hours: Optional[float] = None


class BacklogItemResponse(BaseModel):
    id: str
    title: str
    project_id: Optional[str] = None
    team: Optional[str] = None
    issue_id: Optional[str] = None
    jira_key: Optional[str] = None
    priority: Optional[int] = None
    estimate_hours: Optional[float] = None  # derived sum
    estimate_analyst_hours: Optional[float] = None
    estimate_dev_hours: Optional[float] = None
    estimate_qa_hours: Optional[float] = None
    estimate_opo_hours: Optional[float] = None
    opo_analyst_ratio: Optional[float] = None
    impact: Optional[str] = None
    risk: Optional[str] = None
    archived_at: Optional[datetime] = None
    in_work: bool = False
    approved_scenarios: List[ScenarioRef] = []
    assignee_employee_id: Optional[str] = None
    assignee_display_name: Optional[str] = None
    customer: Optional[str] = None
    cost_type: Optional[str] = None
    # Denormalized Jira status of the linked issue (null for manual items).
    jira_status: Optional[str] = None
    jira_status_category: Optional[str] = None
    jira_status_changed_at: Optional[datetime] = None
    goals: Optional[str] = None
    quarter_label: Optional[str] = None
    # Parallel staffing overrides (NULL = inherit project default).
    parallel_count_analyst: Optional[int] = None
    parallel_count_dev: Optional[int] = None
    parallel_count_qa: Optional[int] = None
    # Planning parameters: effective values (from Jira or manual override).
    involvement_analyst: Optional[float] = None
    involvement_dev: Optional[float] = None
    involvement_qa: Optional[float] = None
    involvement_launch: Optional[float] = None
    duration_analyst_days: Optional[float] = None
    duration_dev_days: Optional[float] = None
    duration_qa_days: Optional[float] = None
    duration_launch_days: Optional[float] = None
    # Current Jira values (for badge "Jira" vs "manual"). May lag local override.
    involvement_analyst_jira: Optional[float] = None
    involvement_dev_jira: Optional[float] = None
    involvement_qa_jira: Optional[float] = None
    involvement_launch_jira: Optional[float] = None
    duration_analyst_days_jira: Optional[float] = None
    duration_dev_days_jira: Optional[float] = None
    duration_qa_days_jira: Optional[float] = None
    duration_launch_days_jira: Optional[float] = None
    # Hierarchy flags for RFA-row expansion in UI.
    planning_mode: str = "whole"
    included_in_planning: bool = True
    has_parent_in_backlog: bool = False
    has_children_in_backlog: bool = False
    children: List[BacklogChildSchema] = []

    class Config:
        from_attributes = True


class LinkJiraRequest(BaseModel):
    jira_key: str


class RefreshResponse(BaseModel):
    created: int
    updated: int
    removed: int = 0  # kept at 0 for backward compat — no more auto-delete
    archived: int = 0
    restored: int = 0
    jira_refreshed: int = 0


# === Helpers ===

def _get_setting_value(db: Session, key: str) -> Optional[str]:
    """Прочитать значение из AppSetting по ключу."""
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else None


async def _discover_field_id(jira, db: Session, setting_key: str, field_name: str) -> Optional[str]:
    """Return Jira custom field ID for field_name, caching result in AppSetting."""
    cached_setting = db.query(AppSetting).filter(AppSetting.key == setting_key).first()
    if cached_setting and cached_setting.value:
        return cached_setting.value
    try:
        fields = await jira.get_fields()
    except Exception:
        return None
    for f in fields:
        if f.get("name", "").strip().lower() == field_name.strip().lower():
            fid = f["id"]
            row = db.query(AppSetting).filter(AppSetting.key == setting_key).first()
            if row:
                row.value = fid
            else:
                db.add(AppSetting(key=setting_key, value=fid))
            db.flush()
            return fid
    return None


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


def _approved_scenarios_for(db: Session, item_id: str) -> List[ScenarioRef]:
    """Return approved scenarios where this backlog item is included (checked).

    Empty list if the item is not allocated/included in any approved scenario.
    """
    rows = (
        db.query(PlanningScenario.id, PlanningScenario.name)
        .join(ScenarioAllocation, ScenarioAllocation.scenario_id == PlanningScenario.id)
        .filter(
            ScenarioAllocation.backlog_item_id == item_id,
            PlanningScenario.status == "approved",
            ScenarioAllocation.included_flag == True,
        )
        .distinct()
        .all()
    )
    return [ScenarioRef(id=i, name=n) for i, n in rows]


def _quarter_labels_bulk(db: Session, item_ids: list[str]) -> dict[str, str]:
    """Один запрос для всех archived items вместо N запросов."""
    if not item_ids:
        return {}
    rows = (
        db.query(
            ScenarioAllocation.backlog_item_id,
            PlanningScenario.quarter,
            PlanningScenario.year,
        )
        .join(PlanningScenario, PlanningScenario.id == ScenarioAllocation.scenario_id)
        .filter(
            ScenarioAllocation.backlog_item_id.in_(item_ids),
            PlanningScenario.status == "approved",
            ScenarioAllocation.included_flag.is_(True),
        )
        .all()
    )
    return {
        bid: f"{q.replace('Q', '')} кв. {y}"
        for bid, q, y in rows
        if q and y
    }


def _to_response(
    item: BacklogItem,
    approved_scenarios: Optional[List[ScenarioRef]] = None,
    quarter_label: Optional[str] = None,
    has_parent_in_backlog: bool = False,
    has_children_in_backlog: bool = False,
    children: Optional[List[BacklogChildSchema]] = None,
) -> BacklogItemResponse:
    scenarios = approved_scenarios or []
    issue = item.issue
    jira_in_progress = bool(issue and issue.status_category == "indeterminate")
    return BacklogItemResponse(
        id=item.id,
        title=item.title,
        project_id=item.project_id,
        team=(issue.team if issue else item.team),
        issue_id=item.issue_id,
        jira_key=issue.key if issue else None,
        priority=item.priority,
        estimate_hours=item.estimate_hours,
        estimate_analyst_hours=item.estimate_analyst_hours,
        estimate_dev_hours=item.estimate_dev_hours,
        estimate_qa_hours=item.estimate_qa_hours,
        estimate_opo_hours=item.estimate_opo_hours,
        opo_analyst_ratio=item.opo_analyst_ratio,
        impact=item.impact,
        risk=item.risk,
        archived_at=item.archived_at,
        in_work=bool(scenarios) or jira_in_progress,
        approved_scenarios=scenarios,
        assignee_employee_id=item.assignee_employee_id,
        assignee_display_name=(
            issue.assignee_display_name if (issue and issue.assignee_display_name) else
            (item.assignee.display_name if item.assignee else None)
        ),
        customer=item.customer,
        cost_type=item.cost_type,
        jira_status=issue.status if issue else None,
        jira_status_category=issue.status_category if issue else None,
        jira_status_changed_at=issue.status_changed_at if issue else None,
        goals=issue.goals if issue else None,
        quarter_label=quarter_label,
        parallel_count_analyst=item.parallel_count_analyst,
        parallel_count_dev=item.parallel_count_dev,
        parallel_count_qa=item.parallel_count_qa,
        involvement_analyst=item.involvement_analyst,
        involvement_dev=item.involvement_dev,
        involvement_qa=item.involvement_qa,
        involvement_launch=item.involvement_launch,
        duration_analyst_days=item.duration_analyst_days,
        duration_dev_days=item.duration_dev_days,
        duration_qa_days=item.duration_qa_days,
        duration_launch_days=item.duration_launch_days,
        involvement_analyst_jira=issue.involvement_analyst if issue else None,
        involvement_dev_jira=issue.involvement_dev if issue else None,
        involvement_qa_jira=issue.involvement_qa if issue else None,
        involvement_launch_jira=issue.involvement_launch if issue else None,
        duration_analyst_days_jira=issue.duration_analyst_days if issue else None,
        duration_dev_days_jira=issue.duration_dev_days if issue else None,
        duration_qa_days_jira=issue.duration_qa_days if issue else None,
        duration_launch_days_jira=issue.duration_launch_days if issue else None,
        planning_mode=item.planning_mode,
        included_in_planning=item.included_in_planning,
        has_parent_in_backlog=has_parent_in_backlog,
        has_children_in_backlog=has_children_in_backlog,
        children=children or [],
    )


# === CRUD ===

@router.get("", response_model=List[BacklogItemResponse])
async def list_backlog_items(
    project_id: Optional[str] = Query(None),
    view: str = Query("active", pattern="^(active|archived|in_work|quarterly)$"),
    teams: Optional[str] = Query(None, description="Comma-separated team codes to filter by"),
    db: Session = Depends(get_db),
):
    """Список бэклога с фильтром по виду.

    - ``active`` (default): не архивные, статус не done.
    - ``archived``: ``archived_at IS NOT NULL`` или статус done.
    - ``in_work``: включены в утверждённый сценарий или статус в работе.
    """
    ParentIssue = aliased(Issue)
    query = (
        db.query(BacklogItem)
        .outerjoin(Issue, BacklogItem.issue_id == Issue.id)
        .outerjoin(ParentIssue, Issue.parent_id == ParentIssue.id)
        .options(
            joinedload(BacklogItem.issue).joinedload(Issue.project),
            joinedload(BacklogItem.assignee),
        )
    )
    if project_id is not None:
        query = query.filter(BacklogItem.project_id == project_id)

    teams_list = [t.strip() for t in (teams or "").split(",") if t.strip()]
    if teams_list:
        # Привязанные к Jira элементы фильтруем по команде задачи; ручные идеи
        # (issue_id IS NULL) — по собственному полю team. Ручные идеи без команды
        # (team IS NULL) показываем всегда, чтобы фильтр их не прятал.
        query = query.filter(
            or_(
                Issue.team.in_(teams_list),
                and_(
                    BacklogItem.issue_id.is_(None),
                    or_(
                        BacklogItem.team.is_(None),
                        BacklogItem.team.in_(teams_list),
                    ),
                ),
            )
        )

    # Cancel-like статусы (Отменено / Cancelled / Rejected) считаем «закрыты»
    # — Jira держит их в statusCategory != 'done', но для backlog'а они мусор.
    # Список явный, потому что SQLite lower()/LIKE не работает на кириллице.
    CANCEL_STATUSES = [
        "Отменено", "Отменена", "Отменён", "Отклонено", "Отклонена",
        "Cancelled", "Canceled", "Rejected", "Won't Do", "Won't Fix",
    ]
    cancel_like = Issue.status.in_(CANCEL_STATUSES)

    if view == "active":
        quarterly_filter = or_(
            func.coalesce(Issue.assigned_category, "") == QUARTERLY_TASKS_CATEGORY,
            func.coalesce(Issue.category, "") == QUARTERLY_TASKS_CATEGORY,
        )
        in_work_ids = (
            db.query(ScenarioAllocation.backlog_item_id)
            .join(PlanningScenario, PlanningScenario.id == ScenarioAllocation.scenario_id)
            .filter(
                PlanningScenario.status == "approved",
                ScenarioAllocation.included_flag == True,
            )
            .distinct()
            .scalar_subquery()
        )
        query = query.filter(
            BacklogItem.archived_at.is_(None),
            func.coalesce(Issue.status_category, "").notin_(["done"]),
            or_(
                BacklogItem.issue_id.is_(None),
                ~quarterly_filter,
            ),
            BacklogItem.id.notin_(in_work_ids),
            # Cancel-like статусы — в архив, не сюда
            or_(
                BacklogItem.issue_id.is_(None),
                ~cancel_like,
            ),
        )
    elif view == "archived":
        # Архив:
        # - явно отправленные в архив (archived_at)
        # - cancel-like ("Отменено") — выкинуты из плана
        # - done initiatives_rfa (выполненные инициативы из бэклога)
        # Done quarterly_tasks остаются в Активных как часть плана.
        query = query.filter(
            or_(
                BacklogItem.archived_at.isnot(None),
                cancel_like,
                and_(
                    Issue.status_category == "done",
                    func.coalesce(Issue.category, "") != QUARTERLY_TASKS_CATEGORY,
                    func.coalesce(Issue.assigned_category, "") != QUARTERLY_TASKS_CATEGORY,
                ),
            ),
        )
    elif view == "in_work":
        in_work_ids = (
            db.query(ScenarioAllocation.backlog_item_id)
            .join(PlanningScenario, PlanningScenario.id == ScenarioAllocation.scenario_id)
            .filter(
                PlanningScenario.status == "approved",
                ScenarioAllocation.included_flag == True,
            )
            .distinct()
            .scalar_subquery()
        )
        query = query.filter(
            BacklogItem.archived_at.is_(None),
            or_(
                BacklogItem.id.in_(in_work_ids),
                Issue.status_category == "indeterminate",
            ),
            # Cancel-like статусы — в архив, не в «В работе»
            or_(
                BacklogItem.issue_id.is_(None),
                ~cancel_like,
            ),
        )
    elif view == "quarterly":
        # Only root-level quarterly tasks — exclude children whose parent is also quarterly
        not_quarterly_parent = or_(
            Issue.parent_id.is_(None),
            ParentIssue.id.is_(None),
            and_(
                func.coalesce(ParentIssue.assigned_category, "") != QUARTERLY_TASKS_CATEGORY,
                func.coalesce(ParentIssue.category, "") != QUARTERLY_TASKS_CATEGORY,
            ),
        )
        query = query.filter(
            BacklogItem.archived_at.is_(None),
            or_(
                Issue.assigned_category == QUARTERLY_TASKS_CATEGORY,
                Issue.category == QUARTERLY_TASKS_CATEGORY,
            ),
            not_quarterly_parent,
            # Только cancel-like прячем (Отменено = выкинуто из плана).
            # status_category='done' (Закрыт/Done) остаётся видимым —
            # это выполненная по плану задача, утверждённая в сценарии.
            or_(
                BacklogItem.issue_id.is_(None),
                ~cancel_like,
            ),
        )

    items = query.all()

    # Скрываем явные leaf-типы (HierarchyRule с is_container=False).
    rules = load_rules(db)

    def _item_is_leaf(it: BacklogItem) -> bool:
        if it.issue_id is None or it.issue is None:
            return False
        issue = it.issue
        project_key = issue.project.key if issue.project else ""
        return is_explicit_leaf(
            rules,
            project_key=project_key,
            issue_type=issue.issue_type or "",
            has_parent=issue.parent_id is not None,
        )

    items = [it for it in items if not _item_is_leaf(it)]

    items.sort(
        key=lambda i: (
            i.priority is None,
            i.priority if i.priority is not None else 0,
            i.title or "",
        )
    )

    # Hierarchy: build issue_id → parent_id map и issue_id → BacklogItem map.
    issue_id_to_item: dict[str, BacklogItem] = {
        bi.issue_id: bi for bi in items if bi.issue_id is not None
    }
    backlog_issue_ids = set(issue_id_to_item.keys())

    if backlog_issue_ids:
        issue_rows = db.query(Issue.id, Issue.parent_id).filter(Issue.id.in_(backlog_issue_ids)).all()
        parent_map = {iid: pid for iid, pid in issue_rows}
        parents_in_backlog = {pid for pid in parent_map.values() if pid is not None and pid in backlog_issue_ids}
    else:
        parent_map = {}
        parents_in_backlog = set()

    # Дочерние issue_id (те, чей parent тоже в backlog) — скрываем из flat-списка.
    child_issue_ids = {
        iid for iid, pid in parent_map.items()
        if pid is not None and pid in backlog_issue_ids
    }

    # Фильтруем: оставляем только корни (не дочки).
    visible_items = [bi for bi in items if bi.issue_id not in child_issue_ids]

    # Строим Map: parent_issue_id → List[BacklogChildSchema].
    children_map: dict[str, list[BacklogChildSchema]] = {}
    for iid, pid in parent_map.items():
        if pid is None or pid not in backlog_issue_ids:
            continue
        child_bi = issue_id_to_item[iid]
        child_issue = child_bi.issue
        schema = BacklogChildSchema(
            id=child_bi.id,
            issue_id=iid,
            key=child_issue.key if child_issue else iid,
            title=child_bi.title,
            issue_type=child_issue.issue_type if child_issue else None,
            status=child_issue.status if child_issue else None,
            included_in_planning=child_bi.included_in_planning,
            estimate_hours=child_bi.estimate_hours,
            estimate_analyst_hours=child_bi.estimate_analyst_hours,
            estimate_dev_hours=child_bi.estimate_dev_hours,
            estimate_qa_hours=child_bi.estimate_qa_hours,
            estimate_opo_hours=child_bi.estimate_opo_hours,
        )
        children_map.setdefault(pid, []).append(schema)

    def _hierarchy_flags(item: BacklogItem):
        iid = item.issue_id
        if iid is None:
            return False, False
        parent_id = parent_map.get(iid)
        has_parent = parent_id is not None and parent_id in backlog_issue_ids
        has_children = iid in parents_in_backlog
        return has_parent, has_children

    def _children_for(item: BacklogItem) -> list[BacklogChildSchema]:
        if item.issue_id is None:
            return []
        return children_map.get(item.issue_id, [])

    if view in ("in_work", "quarterly"):
        labels = _quarter_labels_bulk(db, [i.id for i in visible_items])
        return [
            _to_response(i, _approved_scenarios_for(db, i.id), labels.get(i.id), *_hierarchy_flags(i), _children_for(i))
            for i in visible_items
        ]
    if view == "archived":
        labels = _quarter_labels_bulk(db, [i.id for i in visible_items])
        return [_to_response(i, None, labels.get(i.id), *_hierarchy_flags(i), _children_for(i)) for i in visible_items]
    return [_to_response(i, None, None, *_hierarchy_flags(i), _children_for(i)) for i in visible_items]


@router.post("", response_model=BacklogItemResponse, status_code=201)
async def create_backlog_item(
    data: BacklogItemCreate,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    """Добавить элемент в бэклог."""
    repo = BaseRepository(BacklogItem, db)
    item = repo.create(data.model_dump())
    _recompute_total(item)
    db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["backlog"]})
    db.refresh(item)
    item = (
        db.query(BacklogItem)
        .options(joinedload(BacklogItem.issue), joinedload(BacklogItem.assignee))
        .filter(BacklogItem.id == item.id)
        .first()
    )
    return _to_response(item)


def _backlog_candidate_filter():
    """Фильтр задач-кандидатов в бэклог (целевые + инициативы)."""
    return or_(
        Issue.assigned_category == BACKLOG_CATEGORY,
        Issue.category == BACKLOG_CATEGORY,
        Issue.assigned_category == QUARTERLY_TASKS_CATEGORY,
        Issue.category == QUARTERLY_TASKS_CATEGORY,
    )


async def _perform_refresh(
    db: Session,
    http_request: Optional[Request],
    on_progress: Optional[Callable[[int, int, Optional[str]], Awaitable[None]]] = None,
) -> RefreshResponse:
    """Перечитать с Jira задачи-кандидаты в бэклог и синкнуть BacklogItem.

    Шаги:
      1) Собираем ключи активных/новых кандидатов для похода в Jira
         (архивные элементы бэклога не перечитываем — их поля в анализе не
         участвуют, restore/archive решается локально по резолверу).
      2) ОДИН поход в Jira: ``SyncService.refresh_issues_by_keys`` тянет
         свежие плановые часы / impact / risk / цели / команду + исполнителя
         + заказчика + тип затрат сразу (через ``extra_field_ids`` и коллбек
         ``on_issue``, который обновляет BacklogItem на предзагруженных
         справочниках — без N+1). Если связь с Jira не настроена, шаг
         пропускается и работа продолжается на локальных данных.
      3) Резолвер выступает source of truth и по ходу лечит drift между
         ``assigned_category`` и денормализованным ``category``.
      4) Синк BacklogItem через ``BacklogService.sync_from_issue``.

    ``on_progress(matched, total, current_key)`` — async-коллбек для SSE.

    Возвращает счётчики created / updated / archived / restored / jira_refreshed.
    Исключения (``CancelledError`` / ``JiraClientError``) пробрасываются —
    их разбирает вызывающий эндпоинт.
    """
    resolver = CategoryResolver(db)
    svc = BacklogService(db)
    jira_refreshed = 0

    jira_configured = all(
        _get_setting_value(db, key)
        for key in ("jira_base_url", "jira_email", "jira_api_token")
    )

    # 1) Ключи для Jira — кандидаты, кроме архивных элементов бэклога.
    archived_issue_ids = {
        iid for (iid,) in db.query(BacklogItem.issue_id)
        .filter(BacklogItem.issue_id.isnot(None), BacklogItem.archived_at.isnot(None))
        .all()
    }
    fetch_keys = [
        key for (iid, key) in db.query(Issue.id, Issue.key)
        .filter(_backlog_candidate_filter()).all()
        if iid not in archived_issue_ids
    ]

    # 2) Один поход в Jira за всеми нужными полями сразу.
    if fetch_keys and jira_configured:
        async with JiraClient.from_db(db) as jira:
            customer_field_id = await _discover_field_id(
                jira, db, "jira_customer_field_id", "Заказчик (user)"
            )
            cost_type_field_id = await _discover_field_id(
                jira, db, "jira_cost_type_field_id", "Тип затрат"
            )

            # Предзагрузка справочников одним запросом каждый (без N+1).
            backlog_by_issue = {
                bi.issue_id: bi
                for bi in db.query(BacklogItem)
                .filter(BacklogItem.issue_id.isnot(None)).all()
            }
            emp_by_account = {
                e.jira_account_id: e
                for e in db.query(Employee)
                .filter(Employee.jira_account_id.isnot(None)).all()
            }

            def on_issue(jira_issue, issue_row: Issue) -> None:
                item = backlog_by_issue.get(issue_row.id)
                if item is None:
                    return
                # Исполнитель
                assignee = getattr(jira_issue.fields, "assignee", None)
                account_id = getattr(assignee, "accountId", None) if assignee else None
                if account_id:
                    emp = emp_by_account.get(account_id)
                    item.assignee_employee_id = emp.id if emp else None
                else:
                    item.assignee_employee_id = None
                # Заказчик
                if customer_field_id:
                    raw = (jira_issue.fields._extra or {}).get(customer_field_id)
                    item.customer = (
                        (raw.get("displayName") or raw.get("name"))
                        if isinstance(raw, dict) else None
                    )
                # Тип затрат
                if cost_type_field_id:
                    raw = (jira_issue.fields._extra or {}).get(cost_type_field_id)
                    if isinstance(raw, dict):
                        item.cost_type = raw.get("value") or raw.get("name")
                    elif isinstance(raw, str):
                        item.cost_type = raw
                    else:
                        item.cost_type = None

            checker = None
            if http_request is not None:
                async def checker():
                    return await http_request.is_disconnected()

            service = SyncService(db, jira, cancel_check=checker)
            extra_ids = [f for f in (customer_field_id, cost_type_field_id) if f]
            matched, _total = await service.refresh_issues_by_keys(
                fetch_keys,
                extra_field_ids=extra_ids,
                on_issue=on_issue,
                on_progress=on_progress,
            )
            jira_refreshed = matched
        db.commit()

    # 3) Перечитать кандидатов заново — их ``planned_*`` / impact / risk
    #    теперь актуальны. Сессия могла истечь атрибуты после commit в шаге 2.
    candidates = db.query(Issue).filter(_backlog_candidate_filter()).all()
    created = 0
    updated = 0
    archived = 0
    restored = 0

    for issue in candidates:
        resolved = resolver.resolve_for_issue(issue).category_code
        if issue.category != resolved:
            issue.category = resolved
        if resolved not in (BACKLOG_CATEGORY, QUARTERLY_TASKS_CATEGORY):
            continue
        existing = (
            db.query(BacklogItem).filter_by(issue_id=issue.id).one_or_none()
        )
        was_archived = existing is not None and existing.archived_at is not None
        was_present = existing is not None
        svc.sync_from_issue(issue)
        if was_present:
            updated += 1
            if was_archived:
                restored += 1
        else:
            created += 1

    # Items that used to be backlog but Jira category moved away → archive.
    stale_items = (
        db.query(BacklogItem)
        .options(joinedload(BacklogItem.issue))
        .filter(BacklogItem.issue_id.isnot(None))
        .all()
    )
    for item in stale_items:
        if item.issue is None:
            continue
        resolved = resolver.resolve_for_issue(item.issue).category_code
        if resolved in (BACKLOG_CATEGORY, QUARTERLY_TASKS_CATEGORY):
            continue
        if item.archived_at is None:
            svc.sync_from_issue(item.issue)
            archived += 1

    db.commit()
    return RefreshResponse(
        created=created,
        updated=updated,
        archived=archived,
        restored=restored,
        jira_refreshed=jira_refreshed,
    )


@router.post("/refresh-from-jira", response_model=RefreshResponse)
async def refresh_from_jira(
    http_request: Request,
    db: Session = Depends(get_db),
):
    """Перечитать с Jira кандидатов в бэклог (блокирующий вариант)."""
    try:
        return await _perform_refresh(db, http_request)
    except asyncio.CancelledError:
        raise HTTPException(status_code=499, detail="Refresh cancelled by client")
    except JiraClientError as e:
        raise HTTPException(status_code=502, detail=f"Jira error: {e}")


@router.post("/refresh-from-jira/stream")
async def refresh_from_jira_stream(
    http_request: Request,
    db: Session = Depends(get_db),
):
    """SSE-стрим прогресса «Обновить с Jira».

    События: ``progress`` (matched / total / current_key) по ходу похода в
    Jira, ``done`` с финальными счётчиками, ``error`` — ошибка,
    ``cancelled`` — клиент оборвал соединение (кнопка «Прервать»).
    """
    async def event_gen():
        queue: asyncio.Queue = asyncio.Queue()

        async def on_progress(matched: int, total: int, current_key: Optional[str]) -> None:
            await queue.put({
                "type": "progress",
                "matched": matched,
                "total": total,
                "current_key": current_key,
            })

        async def run() -> None:
            try:
                result = await _perform_refresh(db, http_request, on_progress=on_progress)
                await queue.put({
                    "type": "done",
                    "created": result.created,
                    "updated": result.updated,
                    "archived": result.archived,
                    "restored": result.restored,
                    "jira_refreshed": result.jira_refreshed,
                })
            except asyncio.CancelledError:
                await queue.put({"type": "cancelled"})
                raise
            except JiraClientError as e:
                await queue.put({"type": "error", "detail": f"Jira error: {e}"})
            except Exception as e:
                await queue.put({"type": "error", "detail": str(e)})

        task = asyncio.create_task(run())
        try:
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8")
                if event["type"] in ("done", "error", "cancelled"):
                    break
        finally:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await task

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.get("/{item_id}", response_model=BacklogItemResponse)
async def get_backlog_item(
    item_id: str,
    db: Session = Depends(get_db),
):
    """Получить один элемент бэклога по id."""
    item = (
        db.query(BacklogItem)
        .options(joinedload(BacklogItem.issue), joinedload(BacklogItem.assignee))
        .filter(BacklogItem.id == item_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Backlog item not found")
    return _to_response(item, _approved_scenarios_for(db, item.id))


@router.patch("/{item_id}", response_model=BacklogItemResponse)
async def update_backlog_item(
    item_id: str,
    data: BacklogItemUpdate,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    """Частичное обновление элемента бэклога."""
    item = (
        db.query(BacklogItem)
        .options(joinedload(BacklogItem.issue), joinedload(BacklogItem.assignee))
        .filter(BacklogItem.id == item_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Backlog item not found")

    patch = data.model_dump(exclude_unset=True)
    if not patch:
        return _to_response(item, _approved_scenarios_for(db, item.id))

    for key, value in patch.items():
        setattr(item, key, value)
    _recompute_total(item)
    db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["backlog"]})
    db.refresh(item)
    return _to_response(item, _approved_scenarios_for(db, item.id))


@router.delete("/{item_id}")
async def delete_backlog_item(
    item_id: str,
    db: Session = Depends(get_db),
):
    """Удалить элемент бэклога.

    Каскадно удаляет связанные ``ScenarioAllocation`` у ``draft``-сценариев.
    Если хотя бы один ``approved``-сценарий ссылается на элемент — 409, чтобы
    не дропать согласованный план молча. В ответе перечислим имена таких
    сценариев, чтобы UI мог показать, что блокирует удаление.
    """
    repo = BaseRepository(BacklogItem, db)
    item = repo.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Backlog item not found")

    approved_scenarios = (
        db.query(PlanningScenario)
        .join(ScenarioAllocation, ScenarioAllocation.scenario_id == PlanningScenario.id)
        .filter(
            ScenarioAllocation.backlog_item_id == item_id,
            PlanningScenario.status == "approved",
        )
        .distinct()
        .all()
    )
    if approved_scenarios:
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "Backlog item is referenced by approved planning scenarios; "
                    "revert them to draft or remove the item from each scenario first."
                ),
                "blocking_scenarios": [
                    {"id": s.id, "name": s.name} for s in approved_scenarios
                ],
            },
        )

    affected = (
        db.query(PlanningScenario)
        .join(ScenarioAllocation, ScenarioAllocation.scenario_id == PlanningScenario.id)
        .filter(ScenarioAllocation.backlog_item_id == item_id)
        .distinct()
        .all()
    )
    allocations_removed = (
        db.query(ScenarioAllocation)
        .filter(ScenarioAllocation.backlog_item_id == item_id)
        .delete(synchronize_session=False)
    )

    repo.delete(item)
    db.commit()
    return {
        "status": "deleted",
        "id": item_id,
        "allocations_removed": allocations_removed,
        "affected_scenarios": [{"id": s.id, "name": s.name} for s in affected],
    }


@router.post("/{item_id}/link-jira", response_model=BacklogItemResponse)
async def link_jira(
    item_id: str,
    body: LinkJiraRequest,
    db: Session = Depends(get_db),
):
    """Привязать ручной BacklogItem к Jira-задаче.

    Перетягивает title / project_id / per-role estimates / impact / risk
    из Issue. Локальные ``priority`` / ``opo_analyst_ratio`` не трогаются.
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
        .options(joinedload(BacklogItem.issue), joinedload(BacklogItem.assignee))
        .filter(BacklogItem.id == item_id)
        .first()
    )
    return _to_response(item, _approved_scenarios_for(db, item.id))


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
        .options(joinedload(BacklogItem.issue), joinedload(BacklogItem.assignee))
        .filter(BacklogItem.id == item_id)
        .first()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Backlog item not found")

    item.issue_id = None
    db.commit()
    db.refresh(item)
    return _to_response(item, _approved_scenarios_for(db, item.id))


@router.post("/{item_id}/archive", response_model=BacklogItemResponse)
async def archive_backlog_item(
    item_id: str,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    """Архивировать инициативу — скрыть из активного бэклога.

    422, если элемент в ≥1 утверждённом сценарии. Идемпотентно: повторный
    вызов не меняет ``archived_at``.
    """
    item = (
        db.query(BacklogItem)
        .options(joinedload(BacklogItem.issue), joinedload(BacklogItem.assignee))
        .filter(BacklogItem.id == item_id)
        .first()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Backlog item not found")

    if item.archived_at is None:
        blocking = (
            db.query(PlanningScenario)
            .join(ScenarioAllocation, ScenarioAllocation.scenario_id == PlanningScenario.id)
            .filter(
                ScenarioAllocation.backlog_item_id == item_id,
                PlanningScenario.status == "approved",
            )
            .distinct()
            .all()
        )
        if blocking:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": (
                        "Initiative is allocated to an approved scenario — "
                        "remove the allocation first."
                    ),
                    "blocking_scenarios": [
                        {"id": s.id, "name": s.name} for s in blocking
                    ],
                },
            )
        item.archived_at = datetime.utcnow()
        # Убрать из черновиков сразу — иначе элемент остаётся доступным
        # для включения в план до следующего пересчёта маппинга.
        # Утверждённые сценарии уже отсеяны проверкой выше (HTTP 422).
        draft_ids = [
            sid
            for (sid,) in db.query(PlanningScenario.id)
            .filter(PlanningScenario.status == "draft")
            .all()
        ]
        if draft_ids:
            db.query(ScenarioAllocation).filter(
                ScenarioAllocation.backlog_item_id == item_id,
                ScenarioAllocation.scenario_id.in_(draft_ids),
            ).delete(synchronize_session=False)
        db.commit()
        await event_bus.publish({"type": "entity_changed", "entities": ["backlog", "planning"]})
        db.refresh(item)
    return _to_response(item, _approved_scenarios_for(db, item.id))


class PlanningModeRequest(BaseModel):
    mode: str  # 'whole' | 'by_epics'


class IncludedRequest(BaseModel):
    included: bool


def _reconcile_mode(db: Session, item_id: str) -> None:
    """Синхронизировать draft-allocations элемента с его режимом планирования.

    RFA-родитель «по эпикам» (контекст) — снять его allocations из черновиков;
    иначе — добить (идемпотентно). Выравнивает уже существующие сценарии сразу
    после смены режима, не дожидаясь self-heal при следующем открытии.
    """
    svc = BacklogService(db)
    if item_id in mode_excluded_backlog_ids(db):
        svc._remove_draft_allocations(item_id)
    else:
        svc._ensure_draft_allocations(item_id)


@router.patch("/{item_id}/planning-mode")
async def set_planning_mode(
    item_id: str,
    payload: PlanningModeRequest,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    """Переключить режим планирования RFA: whole (целиком) или by_epics (по эпикам).

    При переходе в «по эпикам» сам RFA-родитель по умолчанию становится
    контекстом (исчезает из сценариев) — в план идут дочерние Эпики. Вернуть
    родителя можно галочкой «Включить саму RFA» (для непокрытых кварталов).
    """
    if payload.mode not in ("whole", "by_epics"):
        raise HTTPException(422, "mode must be 'whole' or 'by_epics'")
    bi = db.query(BacklogItem).filter_by(id=item_id).one_or_none()
    if bi is None:
        raise HTTPException(404, "BacklogItem not found")
    bi.planning_mode = payload.mode
    # by_epics → родитель по умолчанию контекст; whole → флаг участия не нужен.
    bi.included_in_planning = payload.mode != "by_epics"
    db.flush()
    _reconcile_mode(db, item_id)
    result_mode = bi.planning_mode
    result_included = bi.included_in_planning
    db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["backlog", "planning"]})
    return {"id": item_id, "planning_mode": result_mode, "included_in_planning": result_included}


@router.patch("/{item_id}/included")
async def set_included(
    item_id: str,
    payload: IncludedRequest,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    """Включить/исключить RFA-родитель из планирования (режим «по эпикам»)."""
    bi = db.query(BacklogItem).filter_by(id=item_id).one_or_none()
    if bi is None:
        raise HTTPException(404, "BacklogItem not found")
    bi.included_in_planning = payload.included
    db.flush()
    _reconcile_mode(db, item_id)
    result_included = bi.included_in_planning
    db.commit()
    await event_bus.publish({"type": "entity_changed", "entities": ["backlog", "planning"]})
    return {"id": item_id, "included_in_planning": result_included}


@router.post("/{item_id}/restore", response_model=BacklogItemResponse)
async def restore_backlog_item(
    item_id: str,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    """Восстановить инициативу из архива в активный бэклог.

    Если инициатива привязана к Jira-задаче, а в Jira категория сейчас
    архивная — 409: Jira source-of-truth, сначала смените категорию там.
    Идемпотентно: уже активный элемент — no-op.
    """
    item = (
        db.query(BacklogItem)
        .options(joinedload(BacklogItem.issue), joinedload(BacklogItem.assignee))
        .filter(BacklogItem.id == item_id)
        .first()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Backlog item not found")

    if item.archived_at is not None:
        if item.issue is not None and item.issue.category not in TRACKED_CATEGORIES:
            raise HTTPException(
                status_code=409,
                detail=(
                    "В Jira у задачи архивная категория — сначала смените категорию "
                    "в Jira на вкладке «Категории задач»."
                ),
            )
        if item.issue is not None and is_cancel_like(item.issue):
            raise HTTPException(
                status_code=409,
                detail=(
                    "В Jira задача в статусе отмены/отклонения — сначала "
                    "переведите её в активный статус."
                ),
            )
        item.archived_at = None
        db.commit()
        await event_bus.publish({"type": "entity_changed", "entities": ["backlog"]})
        db.refresh(item)
    return _to_response(item, _approved_scenarios_for(db, item.id))
