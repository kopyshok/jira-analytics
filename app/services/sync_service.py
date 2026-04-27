"""Sync service - orchestrates Jira data synchronization."""

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Awaitable, Callable, Optional, List, Tuple, Any
import json
import logging

from sqlalchemy.orm import Session

from app.connectors.jira_client import JiraClient
from app.connectors.schemas import (
    JiraProjectSchema,
    JiraIssueSchema,
    JiraWorklogSchema,
    JiraCommentSchema,
    JiraUserSchema,
)
from app.models import (
    Employee, Project, Issue, Worklog, Comment,
    SyncState, ScopeProject,
)
from app.models.app_setting import AppSetting
from app.repositories.base import BaseRepository


def _extract_team_values(extra: dict, field_id: Optional[str]) -> List[str]:
    """Вытащить значения team-поля из raw ``fields`` (см. JiraIssueFieldsSchema._extra).

    Jira кастомные поля команды встречаются в трёх формах:
    - ``None`` — не установлено
    - ``{"value": "Team A"}`` — single-select
    - ``[{"value": "Team A"}, {"value": "Team B"}]`` — multi-select
    - ``"Team A"`` — plain text (редко)
    """
    if not field_id:
        return []
    value = extra.get(field_id)
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        v = value.get("value")
        return [v] if v else []
    if isinstance(value, list):
        out = []
        for item in value:
            if isinstance(item, dict):
                v = item.get("value")
                if v:
                    out.append(v)
            elif isinstance(item, str):
                out.append(item)
        return out
    return []


def _parse_jira_datetime(raw: Optional[str]) -> Optional[datetime]:
    """Parse Jira timestamp (ISO 8601 with timezone, e.g. ``2026-04-17T10:48:33.357+0000``).

    Returns a naive UTC datetime for storage (SQLite has no timezone type).
    """
    if not raw:
        return None
    try:
        # Python 3.10 fromisoformat can't handle ±HHMM without colon — normalize.
        normalized = raw
        if len(raw) >= 5 and (raw[-5] in "+-") and raw[-3] != ":":
            normalized = raw[:-2] + ":" + raw[-2:]
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except (ValueError, TypeError):
        return None


def _parse_jira_date(raw: Optional[str]) -> Optional[datetime]:
    """Parse Jira plain date (e.g. ``2026-06-30``) into a naive midnight datetime."""
    if not raw:
        return None
    try:
        d = date.fromisoformat(raw)
        return datetime(d.year, d.month, d.day)
    except (ValueError, TypeError):
        return None


logger = logging.getLogger("jira_analytics.sync")


# Planned-effort custom-field AppSetting keys. Populated by admin in /settings.
# Extracted per-issue in _upsert_issue via Jira's ``_extra`` dict.
_PLANNED_NUMERIC_SETTING_KEYS = [
    "jira_planned_analyst_hours_field_id",
    "jira_planned_dev_hours_field_id",
    "jira_planned_qa_hours_field_id",
    "jira_planned_opo_hours_field_id",
    "jira_involvement_analyst_field_id",
    "jira_involvement_dev_field_id",
    "jira_involvement_qa_field_id",
    "jira_involvement_launch_field_id",
    "jira_duration_analyst_field_id",
    "jira_duration_dev_field_id",
    "jira_duration_qa_field_id",
    "jira_duration_launch_field_id",
]
_PLANNED_STRING_SETTING_KEYS = [
    "jira_impact_field_id",
    "jira_risk_field_id",
]
_ALL_PLANNED_KEYS = _PLANNED_NUMERIC_SETTING_KEYS + _PLANNED_STRING_SETTING_KEYS


def _to_float(raw: Any) -> Optional[float]:
    """Coerce a Jira-field value to float. Supports numbers, numeric strings
    with ``.`` or ``,`` decimal separator. Returns ``None`` for anything else."""
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    try:
        return float(str(raw).replace(",", "."))
    except (TypeError, ValueError):
        return None


_LEVEL_MAP = {
    "high": "high", "высокий": "high", "critical": "high", "major": "high",
    "medium": "medium", "средний": "medium", "normal": "medium",
    "low": "low", "низкий": "low", "minor": "low", "trivial": "low",
}


def _normalize_level(raw: Any) -> Optional[str]:
    """Нормализует значение select-поля (impact / risk) к low|medium|high.

    Jira select-поля приходят либо как ``{"value": "...", "id": "..."}``,
    либо как plain string. Неизвестные значения → None.
    """
    if raw is None:
        return None
    value = raw.get("value") if isinstance(raw, dict) else raw
    if not isinstance(value, str):
        return None
    return _LEVEL_MAP.get(value.strip().lower())

# Sentinel, чтобы отличать «поле не передано» от «поле передано с пустым значением».
# None как «пусто» теперь валидный сигнал «очистить в БД».
_UNSET: Any = object()


@dataclass
class ReloadStats:
    """Результат жёсткой перезагрузки worklog'ов по дате начала."""

    deleted: int = 0
    issues_scanned: int = 0
    worklogs_inserted: int = 0


@dataclass
class UpdateStats:
    """Результат мягкого обновления ворклогов (без удаления).

    ``bucket_a_*`` — проход по всем issue с ``updated >= since``.
    ``bucket_b_*`` — проход по ворклогам сотрудников выбранных команд
    (включая задачи вне scope, которые создаются с ``out_of_scope=True``).
    ``touched_issue_keys`` — все Jira-ключи задач, по которым были обновлены
    ворклоги (из обоих вёдер). Используется в team-mode pipeline для
    последующего refresh метаданных задач.
    """

    bucket_a_issues_scanned: int = 0
    bucket_a_worklogs_upserted: int = 0
    bucket_a_worklogs_deleted: int = 0
    bucket_b_issues_scanned: int = 0
    bucket_b_worklogs_upserted: int = 0
    bucket_b_worklogs_deleted: int = 0
    bucket_b_out_of_scope_created: int = 0
    touched_issue_keys: "set[str]" = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.touched_issue_keys is None:
            self.touched_issue_keys = set()

    @property
    def worklogs_upserted(self) -> int:
        return self.bucket_a_worklogs_upserted + self.bucket_b_worklogs_upserted

    @property
    def worklogs_deleted(self) -> int:
        return self.bucket_a_worklogs_deleted + self.bucket_b_worklogs_deleted

    @property
    def deleted(self) -> int:
        # Совместимость с SSE-обёрткой; теперь возвращает реальное число удалённых.
        return self.worklogs_deleted


class SyncStats:
    """Statistics for a sync operation."""
    
    def __init__(self):
        self.projects_synced = 0
        self.projects_created = 0
        self.issues_synced = 0
        self.issues_created = 0
        self.worklogs_synced = 0
        self.worklogs_created = 0
        self.comments_synced = 0
        self.comments_created = 0
        self.employees_synced = 0
        self.employees_created = 0
        self.errors: List[str] = []
        self.started_at = datetime.utcnow()
        self.finished_at: Optional[datetime] = None
    
    def finish(self):
        self.finished_at = datetime.utcnow()
    
    @property
    def duration_seconds(self) -> float:
        end = self.finished_at or datetime.utcnow()
        return (end - self.started_at).total_seconds()
    
    def to_dict(self) -> dict:
        return {
            "projects": {"synced": self.projects_synced, "created": self.projects_created},
            "issues": {"synced": self.issues_synced, "created": self.issues_created},
            "worklogs": {"synced": self.worklogs_synced, "created": self.worklogs_created},
            "comments": {"synced": self.comments_synced, "created": self.comments_created},
            "employees": {"synced": self.employees_synced, "created": self.employees_created},
            "errors": self.errors,
            "duration_seconds": self.duration_seconds,
        }


class SyncService:
    """Service for synchronizing Jira data to local database.
    
    Handles:
    - Incremental sync using SyncState cursors
    - Dependency ordering (employees -> projects -> issues -> worklogs)
    - Upsert logic for all entities
    """
    
    def __init__(
        self,
        db: Session,
        jira_client: JiraClient,
        cancel_check: Optional[Callable[[], Awaitable[bool]]] = None,
    ):
        self.db = db
        self.jira = jira_client
        self.stats = SyncStats()
        # Коллбек проверки отмены от клиента (например request.is_disconnected
        # для HTTP-эндпоинтов). Если None — синк работает без возможности отмены.
        self._cancel_check = cancel_check

        # Initialize repositories
        self.employee_repo = BaseRepository(Employee, db)
        self.project_repo = BaseRepository(Project, db)
        self.issue_repo = BaseRepository(Issue, db)
        self.worklog_repo = BaseRepository(Worklog, db)
        self.comment_repo = BaseRepository(Comment, db)
        self.sync_state_repo = BaseRepository(SyncState, db)
        self.scope_project_repo = BaseRepository(ScopeProject, db)

    async def _check_cancelled(self) -> None:
        """Опрос отмены. Если клиент отвалился — поднимает CancelledError.

        Вставляется в горячие циклы (между страницами Jira, между issue'ами при
        обходе ворклогов/комментов). Обработанные до отмены данные остаются в
        БД — инкрементальный синк итак коммитит прогресс постранично.
        """
        if self._cancel_check is None:
            return
        if await self._cancel_check():
            logger.info("Sync cancelled by client")
            raise asyncio.CancelledError("client disconnected")
    
    def _get_scope_project_keys(self) -> List[str]:
        """Получить список разрешённых ключей проектов из scope_projects.

        Если scope не настроен, возвращает пустой список.
        """
        scope_projects = self.scope_project_repo.get_all(limit=1000)
        return [
            sp.jira_project_key
            for sp in scope_projects
            if sp.is_enabled
        ]

    def _get_sync_state(self, entity_name: str, scope: str = "") -> Optional[SyncState]:
        """Get sync state for ``(entity_name, scope)``.

        ``scope=""`` is the global cursor (the old pre-013 behaviour).
        Non-empty ``scope`` indicates a per-team (or other discriminator)
        cursor — e.g. ``scope="Team X"``.
        """
        from sqlalchemy import select
        stmt = select(SyncState).where(
            SyncState.entity_name == entity_name,
            SyncState.scope == scope,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def _get_setting(self, key: str) -> Optional[str]:
        """Прочитать значение из AppSetting."""
        row = self.db.query(AppSetting).filter(AppSetting.key == key).first()
        return row.value if row else None

    def _configured_planned_field_ids(self) -> List[str]:
        """Список настроенных (непустых) customfield IDs для полей плановых
        трудозатрат, involvement, duration, impact, risk.

        Используется для расширения ``fields=`` параметра в запросах к Jira,
        чтобы эти поля реально возвращались в ответе и попадали в ``_extra``.
        """
        ids: list[str] = []
        seen: set[str] = set()
        for key in _ALL_PLANNED_KEYS:
            fid = self._get_setting(key)
            if fid and fid not in seen:
                ids.append(fid)
                seen.add(fid)
        return ids

    def _resolve_planned_field_ids(self) -> dict[str, Optional[str]]:
        """Резолвит все planned-effort / impact / risk AppSetting ключи один
        раз в начале sync-run, чтобы передавать в ``_upsert_issue`` без N+1.
        """
        return {k: self._get_setting(k) for k in _ALL_PLANNED_KEYS}

    def _update_sync_state(
        self,
        entity_name: str,
        last_success: datetime,
        cursor: Optional[str] = None,
        error: Optional[str] = None,
        scope: str = "",
    ):
        """Update or create sync state row for ``(entity_name, scope)``."""
        state = self._get_sync_state(entity_name, scope)
        data = {
            "entity_name": entity_name,
            "scope": scope,
            "last_success_at": last_success,
            "cursor_value": cursor,
            "last_error": error,
        }
        if state:
            self.sync_state_repo.update(state, data)
        else:
            self.sync_state_repo.create(data)
    
    # === Employee sync ===
    
    def _upsert_employee(self, jira_user: JiraUserSchema) -> Tuple[Employee, bool]:
        """Upsert employee from Jira user."""
        data = {
            "jira_account_id": jira_user.jira_account_id,
            "display_name": jira_user.display_name,
            "email": jira_user.email,
            "is_active": jira_user.is_active,
            "avatar_url": jira_user.avatar_url,
            "synced_at": datetime.utcnow(),
        }
        return self.employee_repo.upsert_by_field(
            "jira_account_id",
            jira_user.jira_account_id,
            data,
        )
    
    def _ensure_employee(self, jira_user: JiraUserSchema) -> Employee:
        """Ensure employee exists, create if not."""
        employee, created = self._upsert_employee(jira_user)
        if created:
            self.stats.employees_created += 1
        self.stats.employees_synced += 1
        return employee
    
    # === Project sync ===
    
    def _upsert_project(self, jira_project: JiraProjectSchema) -> Tuple[Project, bool]:
        """Upsert project from Jira."""
        data = {
            "jira_project_id": jira_project.id,
            "key": jira_project.key,
            "name": jira_project.name,
            "description": jira_project.description,
            "project_type": jira_project.projectTypeKey,
            "synced_at": datetime.utcnow(),
        }
        return self.project_repo.upsert_by_field(
            "jira_project_id",
            jira_project.id,
            data,
        )
    
    async def sync_projects(self) -> int:
        """Синхронизация проектов из Jira.

        Загружает только проекты, включённые в scope_projects.
        Если scope не настроен — загружает все проекты.
        """
        logger.info("Starting projects sync...")
        count = 0
        scope_keys = self._get_scope_project_keys()

        async for jira_project in self.jira.iter_projects():
            await self._check_cancelled()
            # Фильтрация по scope: пропускаем проекты вне scope
            if scope_keys and jira_project.key not in scope_keys:
                continue

            project, created = self._upsert_project(jira_project)
            if created:
                self.stats.projects_created += 1
            self.stats.projects_synced += 1
            count += 1

            if count % 10 == 0:
                logger.debug(f"Synced {count} projects...")

        self._update_sync_state("projects", datetime.utcnow())
        self.db.commit()

        logger.info(f"Projects sync complete: {count} synced, {self.stats.projects_created} created")
        return count
    
    # === Issue sync ===
    
    def _get_project_by_jira_id(self, jira_project_id: str) -> Optional[Project]:
        """Get local project by Jira project ID."""
        return self.project_repo.get_by_field("jira_project_id", jira_project_id)
    
    def _get_issue_by_jira_id(self, jira_issue_id: str) -> Optional[Issue]:
        """Get local issue by Jira issue ID."""
        return self.issue_repo.get_by_field("jira_issue_id", jira_issue_id)
    
    def _upsert_issue(
        self,
        jira_issue: JiraIssueSchema,
        project_id: str,
        parent_id: Optional[str] = None,
        team: Any = _UNSET,
        participating_teams: Any = _UNSET,
        goals: Any = _UNSET,
        planned_field_ids: Optional[dict[str, Optional[str]]] = None,
    ) -> Tuple[Issue, bool]:
        """Upsert issue from Jira.

        ``team`` / ``participating_teams`` / ``goals`` принимают ``_UNSET``
        чтобы означать «колонку не трогать». Явный ``None`` / ``[]`` / ``""``
        от вызывающего — это «очистить значение в БД» (когда поле
        очищено в Jira).

        ``planned_field_ids`` — pre-resolved mapping из `_ALL_PLANNED_KEYS` в
        значения AppSetting, передаётся из вызывающего sync-метода чтобы
        избежать N+1 SELECT'ов на каждой задаче. Если ``None`` — резолвим
        inline (fallback для обратной совместимости).
        """
        status_category = None
        if jira_issue.fields.status.statusCategory:
            status_category = jira_issue.fields.status.statusCategory.get("key")
        data = {
            "jira_issue_id": jira_issue.id,
            "key": jira_issue.key,
            "summary": jira_issue.fields.summary,
            "description": jira_issue.fields.description_text,
            "issue_type": jira_issue.fields.issuetype.name,
            "status": jira_issue.fields.status.name,
            "status_category": status_category,
            "priority": jira_issue.fields.priority.name if jira_issue.fields.priority else None,
            "project_id": project_id,
            "parent_id": parent_id,
            "status_changed_at": _parse_jira_datetime(jira_issue.fields.statuscategorychangedate),
            "due_date": _parse_jira_date(jira_issue.fields.duedate),
            "synced_at": datetime.utcnow(),
        }
        if team is not _UNSET:
            data["team"] = team
        if participating_teams is not _UNSET:
            data["participating_teams"] = json.dumps(
                participating_teams or [], ensure_ascii=False
            )
        if goals is not _UNSET:
            data["goals"] = goals

        # Planned effort / impact / risk — extract from _extra if the matching
        # AppSetting field id is configured. Empty or unset ids → no-op (NULL).
        extra = getattr(jira_issue.fields, "_extra", None) or {}
        if planned_field_ids is None:
            # Fallback: резолвим per-issue (медленно — N+1). Основные sync-методы
            # должны передавать pre-resolved dict.
            planned_ids = {k: self._get_setting(k) for k in _ALL_PLANNED_KEYS}
        else:
            planned_ids = planned_field_ids

        def _fld_float(key: str) -> Optional[float]:
            fid = planned_ids.get(key)
            if not fid:
                return None
            return _to_float(extra.get(fid))

        def _fld_level(key: str) -> Optional[str]:
            fid = planned_ids.get(key)
            if not fid:
                return None
            return _normalize_level(extra.get(fid))

        data["assignee_display_name"] = (
            jira_issue.fields.assignee.display_name
            if jira_issue.fields.assignee else None
        )

        data["planned_analyst_hours"] = _fld_float("jira_planned_analyst_hours_field_id")
        data["planned_dev_hours"] = _fld_float("jira_planned_dev_hours_field_id")
        data["planned_qa_hours"] = _fld_float("jira_planned_qa_hours_field_id")
        data["planned_opo_hours"] = _fld_float("jira_planned_opo_hours_field_id")
        data["involvement_analyst"] = _fld_float("jira_involvement_analyst_field_id")
        data["involvement_dev"] = _fld_float("jira_involvement_dev_field_id")
        data["involvement_qa"] = _fld_float("jira_involvement_qa_field_id")
        data["involvement_launch"] = _fld_float("jira_involvement_launch_field_id")
        data["duration_analyst_days"] = _fld_float("jira_duration_analyst_field_id")
        data["duration_dev_days"] = _fld_float("jira_duration_dev_field_id")
        data["duration_qa_days"] = _fld_float("jira_duration_qa_field_id")
        data["duration_launch_days"] = _fld_float("jira_duration_launch_field_id")
        data["impact"] = _fld_level("jira_impact_field_id")
        data["risk"] = _fld_level("jira_risk_field_id")

        return self.issue_repo.upsert_by_field(
            "jira_issue_id",
            jira_issue.id,
            data,
        )
    
    async def sync_issues(
        self,
        project_keys: Optional[List[str]] = None,
        incremental: bool = True,
    ) -> int:
        """Синхронизация задач из Jira.

        Если project_keys не передан, использует scope_projects.
        Если scope пуст, загружает все локальные проекты.
        """
        logger.info(f"Starting issues sync (incremental={incremental})...")

        # Get projects to sync: explicit keys > scope > all local
        if not project_keys:
            project_keys = self._get_scope_project_keys()

        if project_keys:
            projects = [
                self.project_repo.get_by_field("key", key)
                for key in project_keys
            ]
            projects = [p for p in projects if p]
        else:
            projects = self.project_repo.get_all(limit=1000)
        
        if not projects:
            logger.warning("No projects to sync")
            return 0

        keys = [p.key for p in projects]
        logger.info(f"Syncing issues for {len(keys)} projects: {keys[:5]}...")

        # Get last sync time for incremental
        since = None
        if incremental:
            state = self._get_sync_state("issues")
            if state and state.last_success_at:
                since = state.last_success_at
                logger.info(f"Incremental sync since {since}")

        # Read team/goals field IDs from AppSetting — if configured, request them from Jira
        product_field_id = self._get_setting("jira_team_field_id")
        participating_field_id = self._get_setting("jira_participating_teams_field_id")
        goals_field_id = self._get_setting("jira_goals_field_id")
        extra_fields = [
            fid for fid in (product_field_id, participating_field_id, goals_field_id) if fid
        ]
        # Also request planned-effort / impact / risk custom fields when configured.
        for fid in self._configured_planned_field_ids():
            if fid not in extra_fields:
                extra_fields.append(fid)
        # Resolve planned-effort AppSetting ids once, reuse for every issue.
        planned_field_ids = self._resolve_planned_field_ids()

        count = 0
        unresolved_parents: List[Tuple[str, str]] = []  # (child_issue_id, parent_key)
        async for jira_issue in self.jira.get_issues_updated_since(
            project_keys=keys,
            since=since,
            extra_fields=extra_fields,
        ):
            await self._check_cancelled()
            # Find local project
            project = self._get_project_by_jira_id(jira_issue.fields.project.id)
            if not project:
                logger.warning(f"Project not found for issue {jira_issue.key}")
                continue

            # Handle parent (for subtasks)
            parent_id = None
            parent_key = jira_issue.fields.parent_key
            if parent_key:
                parent = self.issue_repo.get_by_field("key", parent_key)
                if parent:
                    parent_id = parent.id

            # Ensure creator exists as employee
            if jira_issue.fields.creator:
                self._ensure_employee(jira_issue.fields.creator)

            # Собираем только те поля, что реально сконфигурированы,
            # чтобы не затирать колонки в БД, когда админ не задал field_id.
            # Пустое значение в Jira (None / []) сюда приходит как явный
            # сигнал «очистить» — см. _upsert_issue.
            extra_kwargs: dict[str, Any] = {}
            if extra_fields:
                extra = jira_issue.fields._extra
                if product_field_id:
                    prod = _extract_team_values(extra, product_field_id)
                    extra_kwargs["team"] = prod[0] if prod else None
                if participating_field_id:
                    extra_kwargs["participating_teams"] = _extract_team_values(
                        extra, participating_field_id
                    )
                if goals_field_id:
                    goals_list = _extract_team_values(extra, goals_field_id)
                    extra_kwargs["goals"] = ", ".join(goals_list) if goals_list else ""

            # Upsert issue
            issue, created = self._upsert_issue(
                jira_issue, project.id, parent_id,
                planned_field_ids=planned_field_ids,
                **extra_kwargs,
            )
            if created:
                self.stats.issues_created += 1
            self.stats.issues_synced += 1
            count += 1

            # Отложенно свяжем, если родитель ещё не подтянут (обычно эпик
            # приходит позже подзадачи в выдаче /search).
            if parent_key and parent_id is None:
                unresolved_parents.append((issue.id, parent_key))

            if count % 50 == 0:
                logger.debug(f"Synced {count} issues...")
                self.db.commit()  # Periodic commit

        # Второй проход: теперь все эпики уже в базе, достроим parent_id.
        if unresolved_parents:
            resolved = 0
            for child_id, parent_key in unresolved_parents:
                parent = self.issue_repo.get_by_field("key", parent_key)
                if not parent:
                    continue
                child = self.issue_repo.get(child_id)
                if child and child.parent_id != parent.id:
                    child.parent_id = parent.id
                    resolved += 1
            if resolved:
                logger.info(f"Linked {resolved} issues to their parents in second pass")

        self._update_sync_state("issues", datetime.utcnow())
        self.db.commit()

        logger.info(f"Issues sync complete: {count} synced, {self.stats.issues_created} created")
        return count

    async def refresh_issues_by_keys(self, jira_keys: List[str]) -> Tuple[int, int]:
        """Точечная синхронизация: перечитать с Jira только переданные ключи.

        Полезно, когда нужно дотащить новое поле (например,
        ``status_changed_at``) по уже существующему набору задач без
        полной пересинхронизации. Новые задачи НЕ создаются — если
        ключа нет локально, он молча пропускается.

        Returns ``(matched, total_requested)``.
        """
        if not jira_keys:
            return 0, 0

        product_field_id = self._get_setting("jira_team_field_id")
        participating_field_id = self._get_setting("jira_participating_teams_field_id")
        goals_field_id = self._get_setting("jira_goals_field_id")
        extra_fields = [
            fid for fid in (product_field_id, participating_field_id, goals_field_id) if fid
        ]
        for fid in self._configured_planned_field_ids():
            if fid not in extra_fields:
                extra_fields.append(fid)
        planned_field_ids = self._resolve_planned_field_ids()
        base_fields = [
            "summary", "description", "issuetype", "status",
            "priority", "project", "parent", "creator",
            "assignee", "created", "updated",
            "statuscategorychangedate", "duedate",
        ]
        fields = base_fields + list(extra_fields)

        BATCH = 100
        matched = 0
        total = len(jira_keys)
        logger.info(f"Refreshing {total} issues by key (batch={BATCH})")

        for i in range(0, total, BATCH):
            await self._check_cancelled()
            batch = jira_keys[i:i + BATCH]
            keys_jql = ", ".join(f'"{k}"' for k in batch)
            jql = f"key in ({keys_jql})"

            async for jira_issue in self.jira.iter_issues(
                jql=jql,
                max_results=BATCH,
                fields=fields,
            ):
                existing = self.issue_repo.get_by_field("jira_issue_id", jira_issue.id)
                if not existing:
                    continue

                project = self._get_project_by_jira_id(jira_issue.fields.project.id)
                if not project:
                    continue

                parent_id = None
                parent_key = jira_issue.fields.parent_key
                if parent_key:
                    parent = self.issue_repo.get_by_field("key", parent_key)
                    if parent:
                        parent_id = parent.id

                if jira_issue.fields.creator:
                    self._ensure_employee(jira_issue.fields.creator)

                extra_kwargs: dict[str, Any] = {}
                if extra_fields:
                    extra = jira_issue.fields._extra
                    if product_field_id:
                        prod = _extract_team_values(extra, product_field_id)
                        extra_kwargs["team"] = prod[0] if prod else None
                    if participating_field_id:
                        extra_kwargs["participating_teams"] = _extract_team_values(
                            extra, participating_field_id
                        )
                    if goals_field_id:
                        goals_list = _extract_team_values(extra, goals_field_id)
                        extra_kwargs["goals"] = ", ".join(goals_list) if goals_list else ""

                self._upsert_issue(
                    jira_issue, project.id, parent_id,
                    planned_field_ids=planned_field_ids,
                    **extra_kwargs,
                )
                matched += 1

            self.db.commit()
            logger.debug(f"Refreshed {matched} issues so far ({i + len(batch)}/{total} keys processed)")

        logger.info(f"Refresh complete: {matched} of {total} updated")
        return matched, total

    async def sync_team_issues(self, teams: List[str]) -> dict:
        """Подтянуть новые/изменённые задачи выбранных команд за день.

        Для каждой команды строим JQL вида
        ``project in (scope) AND (cf[X]="team" OR cf[Y]="team")
        AND updated >= "<team-cursor>"`` и идём по страницам Jira.
        Курсор хранится в ``sync_state(entity_name="issues", scope=<team>)``
        и обновляется только на успех. Новые задачи создаются, изменённые —
        апдейтятся через штатный ``_upsert_issue``.

        Returns dict ``{team_name: {"matched": N, "created": M, "since": iso|null}}``.
        """
        if not teams:
            return {}

        product_field_id = self._get_setting("jira_team_field_id")
        participating_field_id = self._get_setting("jira_participating_teams_field_id")
        goals_field_id = self._get_setting("jira_goals_field_id")
        extra_fields = [
            fid for fid in (product_field_id, participating_field_id, goals_field_id) if fid
        ]
        for fid in self._configured_planned_field_ids():
            if fid not in extra_fields:
                extra_fields.append(fid)
        planned_field_ids = self._resolve_planned_field_ids()

        # Dedupe field ids when product/participating point to the same column
        # (common in this tenant — both = customfield_11526).
        team_field_ids: list[str] = []
        for fid in (product_field_id, participating_field_id):
            if fid and fid not in team_field_ids:
                team_field_ids.append(fid)
        if not team_field_ids:
            raise ValueError(
                "Не настроены поля команды в AppSetting "
                "('jira_team_field_id' / 'jira_participating_teams_field_id')"
            )

        scope_keys = self._get_scope_project_keys()
        if not scope_keys:
            raise ValueError("Scope проектов пуст — нечего синхронизировать")

        base_fields = [
            "summary", "description", "issuetype", "status",
            "priority", "project", "parent", "creator",
            "assignee", "created", "updated",
            "statuscategorychangedate", "duedate",
        ]
        request_fields = base_fields + list(extra_fields)

        projects_jql = ", ".join(f'"{k}"' for k in scope_keys)

        report: dict = {}
        for team in teams:
            await self._check_cancelled()
            state = self._get_sync_state("issues", scope=team)
            since = state.last_success_at if state else None
            run_start = datetime.utcnow()

            team_escaped = team.replace('"', '\\"')
            cf_clauses = [self._team_jql_clause(fid, team_escaped) for fid in team_field_ids]
            team_clause = cf_clauses[0] if len(cf_clauses) == 1 else "(" + " OR ".join(cf_clauses) + ")"
            jql = f"project in ({projects_jql}) AND {team_clause}"
            if since:
                jql += f' AND updated >= "{since.strftime("%Y-%m-%d %H:%M")}"'
            jql += " ORDER BY updated ASC"

            logger.info(f"Team sync [{team}]: JQL={jql!r}")
            matched = 0
            created = 0
            try:
                async for jira_issue in self.jira.iter_issues(
                    jql=jql,
                    max_results=100,
                    fields=request_fields,
                ):
                    await self._check_cancelled()
                    project = self._get_project_by_jira_id(jira_issue.fields.project.id)
                    if not project:
                        continue

                    parent_id = None
                    parent_key = jira_issue.fields.parent_key
                    if parent_key:
                        parent = self.issue_repo.get_by_field("key", parent_key)
                        if parent:
                            parent_id = parent.id

                    if jira_issue.fields.creator:
                        self._ensure_employee(jira_issue.fields.creator)

                    extra_kwargs: dict[str, Any] = {}
                    extra = jira_issue.fields._extra
                    if product_field_id:
                        prod = _extract_team_values(extra, product_field_id)
                        extra_kwargs["team"] = prod[0] if prod else None
                    if participating_field_id:
                        extra_kwargs["participating_teams"] = _extract_team_values(
                            extra, participating_field_id
                        )
                    if goals_field_id:
                        goals_list = _extract_team_values(extra, goals_field_id)
                        extra_kwargs["goals"] = ", ".join(goals_list) if goals_list else ""

                    _, was_created = self._upsert_issue(
                        jira_issue, project.id, parent_id,
                        planned_field_ids=planned_field_ids,
                        **extra_kwargs,
                    )
                    matched += 1
                    if was_created:
                        created += 1

                    if matched % 50 == 0:
                        self.db.commit()
                # Successful run — move cursor forward. Buffer by 1 minute to
                # cover any issue whose `updated` lands in the same minute as
                # run_start (Jira JQL compares at minute granularity).
                buffered = run_start.replace(second=0, microsecond=0)
                # subtract 60s
                from datetime import timedelta
                cursor = buffered - timedelta(minutes=1)
                self._update_sync_state(
                    "issues", cursor, scope=team, error=None,
                )
                self.db.commit()
                report[team] = {
                    "matched": matched,
                    "created": created,
                    "since": since.isoformat() if since else None,
                }
            except Exception as exc:  # keep running for other teams
                logger.exception(f"Team sync [{team}] failed")
                self.db.rollback()
                # Record the error on the team's cursor row (don't move it).
                prev_since = state.last_success_at if state else None
                self._update_sync_state(
                    "issues",
                    prev_since or datetime.utcfromtimestamp(0),
                    scope=team,
                    error=str(exc)[:2000],
                )
                self.db.commit()
                report[team] = {"matched": matched, "created": created, "error": str(exc)}

        return report

    @staticmethod
    def _team_jql_clause(field_id: str, team_value: str) -> str:
        """Build a JQL equality clause for a Jira custom team field.

        ``field_id`` is the AppSetting value (e.g. ``"customfield_11526"``);
        Jira JQL expects ``cf[11526]`` numeric notation. Falls back to the
        raw id in quotes if parsing fails — works for named fields.
        """
        numeric = field_id.split("_")[-1]
        if numeric.isdigit():
            return f'cf[{numeric}] = "{team_value}"'
        return f'"{field_id}" = "{team_value}"'

    # === Worklog sync ===
    
    def _get_employee_by_jira_id(self, jira_account_id: str) -> Optional[Employee]:
        """Get local employee by Jira account ID."""
        return self.employee_repo.get_by_field("jira_account_id", jira_account_id)
    
    def _upsert_worklog(
        self,
        jira_worklog: JiraWorklogSchema,
        issue_id: str,
        employee_id: str,
    ) -> Tuple[Worklog, bool]:
        """Upsert worklog from Jira."""
        data = {
            "jira_worklog_id": jira_worklog.id,
            "started_at": jira_worklog.started_datetime,
            "hours": jira_worklog.hours,
            "time_spent_seconds": jira_worklog.timeSpentSeconds,
            "comment_text": jira_worklog.comment_text,
            "issue_id": issue_id,
            "employee_id": employee_id,
            "synced_at": datetime.utcnow(),
        }
        return self.worklog_repo.upsert_by_field(
            "jira_worklog_id",
            jira_worklog.id,
            data,
        )
    
    async def sync_worklogs(
        self,
        issue_keys: Optional[List[str]] = None,
        limit_issues: Optional[int] = None,
    ) -> int:
        """Sync worklogs for issues.

        Args:
            issue_keys: Specific issue keys to sync worklogs for.
                       If None, syncs worklogs for all locally synced issues.
            limit_issues: Опционально — верхний предел числа задач. Если не
                задан, обходим весь бэклог задач (без тихого ограничения).
        """
        logger.info("Starting worklogs sync...")

        # Get issues to sync worklogs for
        if issue_keys:
            issues = [
                self.issue_repo.get_by_field("key", key)
                for key in issue_keys
            ]
            issues = [i for i in issues if i]
        else:
            query = self.db.query(Issue)
            if limit_issues is not None:
                query = query.limit(limit_issues)
            issues = query.all()
        
        logger.info(f"Syncing worklogs for {len(issues)} issues...")
        
        count = 0
        for idx, issue in enumerate(issues):
            await self._check_cancelled()
            try:
                async for jira_worklog in self.jira.iter_worklogs_for_issue(
                    issue_id=issue.jira_issue_id
                ):
                    # Ensure author exists as employee
                    author_schema = JiraUserSchema(
                        accountId=jira_worklog.author.accountId,
                        displayName=jira_worklog.author.displayName,
                        emailAddress=jira_worklog.author.emailAddress,
                        active=True,
                    )
                    employee = self._ensure_employee(author_schema)

                    # Upsert worklog
                    worklog, created = self._upsert_worklog(
                        jira_worklog,
                        issue.id,
                        employee.id,
                    )
                    if created:
                        self.stats.worklogs_created += 1
                    self.stats.worklogs_synced += 1
                    count += 1
                
            except Exception as e:
                error_msg = f"Error syncing worklogs for {issue.key}: {e}"
                logger.error(error_msg)
                self.stats.errors.append(error_msg)
            
            if (idx + 1) % 20 == 0:
                logger.debug(f"Processed worklogs for {idx + 1}/{len(issues)} issues...")
                self.db.commit()
        
        self._update_sync_state("worklogs", datetime.utcnow())
        self.db.commit()
        
        logger.info(f"Worklogs sync complete: {count} synced, {self.stats.worklogs_created} created")
        return count
    
    # === Comment sync ===

    def _upsert_comment(
        self,
        jira_comment: JiraCommentSchema,
        issue_id: str,
        author_id: Optional[str] = None,
    ) -> Tuple[Comment, bool]:
        """Upsert comment from Jira."""
        data = {
            "jira_comment_id": jira_comment.id,
            "body": jira_comment.body_text,
            "jira_created_at": jira_comment.created_datetime,
            "issue_id": issue_id,
            "author_id": author_id,
            "synced_at": datetime.utcnow(),
        }
        return self.comment_repo.upsert_by_field(
            "jira_comment_id",
            jira_comment.id,
            data,
        )

    async def sync_comments(
        self,
        issue_keys: Optional[List[str]] = None,
        limit_issues: Optional[int] = None,
    ) -> int:
        """Синхронизация комментариев к задачам.

        Args:
            issue_keys: Конкретные ключи задач. Если None — все локальные задачи.
            limit_issues: Опциональный верхний предел числа задач. Без значения
                обходим все локальные задачи (без тихого ограничения).
        """
        logger.info("Starting comments sync...")

        if issue_keys:
            issues = [
                self.issue_repo.get_by_field("key", key)
                for key in issue_keys
            ]
            issues = [i for i in issues if i]
        else:
            query = self.db.query(Issue)
            if limit_issues is not None:
                query = query.limit(limit_issues)
            issues = query.all()

        logger.info(f"Syncing comments for {len(issues)} issues...")

        count = 0
        for idx, issue in enumerate(issues):
            await self._check_cancelled()
            try:
                async for jira_comment in self.jira.iter_comments_for_issue(
                    issue_id=issue.jira_issue_id
                ):
                    # Ensure author exists as employee
                    author_schema = JiraUserSchema(
                        accountId=jira_comment.author.accountId,
                        displayName=jira_comment.author.displayName,
                        emailAddress=jira_comment.author.emailAddress,
                        active=True,
                    )
                    employee = self._ensure_employee(author_schema)

                    comment, created = self._upsert_comment(
                        jira_comment,
                        issue.id,
                        employee.id,
                    )
                    if created:
                        self.stats.comments_created += 1
                    self.stats.comments_synced += 1
                    count += 1

            except Exception as e:
                error_msg = f"Error syncing comments for {issue.key}: {e}"
                logger.error(error_msg)
                self.stats.errors.append(error_msg)

            if (idx + 1) % 20 == 0:
                logger.debug(f"Processed comments for {idx + 1}/{len(issues)} issues...")
                self.db.commit()

        self._update_sync_state("comments", datetime.utcnow())
        self.db.commit()

        logger.info(f"Comments sync complete: {count} synced, {self.stats.comments_created} created")
        return count

    # === Full sync ===
    
    async def full_sync(
        self,
        project_keys: Optional[List[str]] = None,
        incremental: bool = True,
    ) -> SyncStats:
        """Полная синхронизация в правильном порядке.

        Порядок: Projects -> Issues -> Worklogs -> Comments
        (Employees создаются автоматически при встрече)
        Фильтрация по scope_projects, если project_keys не передан.
        """
        logger.info("Starting full sync...")
        self.stats = SyncStats()

        try:
            # 1. Sync projects (filtered by scope)
            await self.sync_projects()

            # 2. Sync issues (filtered by scope)
            await self.sync_issues(
                project_keys=project_keys,
                incremental=incremental,
            )

            # 3. Sync worklogs
            await self.sync_worklogs()

            # 4. Sync comments
            await self.sync_comments()

        except Exception as e:
            error_msg = f"Full sync failed: {e}"
            logger.error(error_msg)
            self.stats.errors.append(error_msg)
            raise
        finally:
            self.stats.finish()

        logger.info(f"Full sync complete in {self.stats.duration_seconds:.1f}s")
        return self.stats

    async def reload_worklogs_since(
        self,
        since: date,
        on_progress: Optional[
            Callable[["ReloadStats", Optional[str]], Awaitable[None]]
        ] = None,
    ) -> ReloadStats:
        """Удаляет worklog'и с ``started_at >= since`` и перечитывает их
        из Jira по JQL ``worklogDate >= since``.

        Перебирает только те issue, что уже есть в локальной БД: незнакомые
        пропускаются, чтобы не расширять scope молча. Не трогает
        ``sync_state.last_sync``.

        ``on_progress`` — опциональный async-коллбек, вызывается после коммита
        каждого обработанного issue: ``(stats, current_jira_key)``. Используется
        SSE-эндпоинтом для стрима прогресса; для пропущенных (незнакомых) issue
        не вызывается.
        """
        since_dt = datetime.combine(since, datetime.min.time())
        since_dt_aware = since_dt.replace(tzinfo=timezone.utc)
        deleted = (
            self.db.query(Worklog)
            .filter(Worklog.started_at >= since_dt)
            .delete(synchronize_session=False)
        )
        self.db.commit()

        stats = ReloadStats(deleted=deleted)
        if on_progress is not None:
            await on_progress(stats, None)
        jql = f'worklogDate >= "{since.isoformat()}"'

        async for jira_issue in self.jira.iter_issues(
            jql,
            fields=["summary", "issuetype", "status", "project"],
            max_results=100,
        ):
            await self._check_cancelled()
            local = (
                self.db.query(Issue)
                .filter(Issue.jira_issue_id == jira_issue.id)
                .one_or_none()
            )
            if local is None:
                continue
            stats.issues_scanned += 1
            async for wl in self.jira.iter_worklogs_for_issue(jira_issue.id):
                started = wl.started_datetime
                if started.tzinfo is None:
                    started_aware = started.replace(tzinfo=timezone.utc)
                else:
                    started_aware = started
                if started_aware < since_dt_aware:
                    continue
                author_schema = JiraUserSchema(
                    accountId=wl.author.accountId,
                    displayName=wl.author.displayName,
                    emailAddress=wl.author.emailAddress,
                    active=True,
                )
                employee = self._ensure_employee(author_schema)
                _, created = self._upsert_worklog(wl, local.id, employee.id)
                if created:
                    stats.worklogs_inserted += 1
            self.db.commit()
            if on_progress is not None:
                await on_progress(stats, jira_issue.key)

        return stats

    async def update_worklogs_since(
        self,
        since: date,
        teams: Optional[List[str]] = None,
        on_progress: Optional[
            Callable[["UpdateStats", Optional[str]], Awaitable[None]]
        ] = None,
    ) -> "UpdateStats":
        """Мягкое обновление ворклогов: upsert + per-issue delete diff.

        - **Ведро A** (всегда): JQL ``updated >= since``. Для каждого issue,
          уже существующего локально, перечитываются все ворклоги из Jira и
          upsert'ятся. Ворклоги, отсутствующие в Jira, удаляются из локальной БД.
          Незнакомые issue пропускаются.
        - **Ведро B** (если ``teams`` задан): JQL
          ``worklogAuthor = <id> AND updated >= since`` по каждому сотруднику
          из ``employee_teams.team IN teams``. Незнакомые issue создаются
          с ``out_of_scope=True``. Аналогичный delete diff применяется ко всем
          ворклогам задачи (не только от текущего автора).

        Не трогает ``sync_state``. Прогресс — через
        ``on_progress(stats, current_key)``.
        """
        stats = UpdateStats()
        since_iso = since.isoformat()

        # ─── Ведро A ───
        jql_a = f'updated >= "{since_iso}"'
        async for jira_issue in self.jira.iter_issues(
            jql_a,
            fields=["summary", "issuetype", "status", "project"],
            max_results=100,
        ):
            await self._check_cancelled()
            local = (
                self.db.query(Issue)
                .filter(Issue.jira_issue_id == jira_issue.id)
                .one_or_none()
            )
            if local is None:
                continue
            stats.bucket_a_issues_scanned += 1
            jira_wl_ids: set[str] = set()
            async for wl in self.jira.iter_worklogs_for_issue(jira_issue.id):
                await self._check_cancelled()
                jira_wl_ids.add(wl.id)
                author_schema = JiraUserSchema(
                    accountId=wl.author.accountId,
                    displayName=wl.author.displayName,
                    emailAddress=wl.author.emailAddress,
                    active=True,
                )
                employee = self._ensure_employee(author_schema)
                self._upsert_worklog(wl, local.id, employee.id)
                stats.bucket_a_worklogs_upserted += 1
            # Delete diff: удаляем ворклоги, которых уже нет в Jira
            if jira_wl_ids:
                local_wl_ids: set[str] = {
                    row[0]
                    for row in self.db.query(Worklog.jira_worklog_id).filter(
                        Worklog.issue_id == local.id
                    ).all()
                }
                stale_ids = local_wl_ids - jira_wl_ids
                if stale_ids:
                    deleted_count = (
                        self.db.query(Worklog)
                        .filter(
                            Worklog.issue_id == local.id,
                            Worklog.jira_worklog_id.in_(stale_ids),
                        )
                        .delete(synchronize_session=False)
                    )
                    stats.bucket_a_worklogs_deleted += deleted_count
            stats.touched_issue_keys.add(jira_issue.key)
            self.db.commit()
            if on_progress is not None:
                await on_progress(stats, jira_issue.key)

        # ─── Ведро B ───
        if teams:
            await self._update_worklogs_bucket_b(
                since_iso, teams, stats, on_progress,
            )

        return stats

    async def update_worklogs_v2(
        self,
        since: date,
        teams: Optional[List[str]] = None,
        on_progress: Optional[
            Callable[["UpdateStats", Optional[str]], Awaitable[None]]
        ] = None,
    ) -> "UpdateStats":
        """Worklog sync через bulk API (worklog/updated → worklog/list).

        Вместо Bucket A per-issue, использует:
        1. GET /worklog/updated — все изменённые worklog ID за период
        2. POST /worklog/list — батч-загрузка содержимого
        3. Upsert только для issue которые есть в локальной БД
        4. Delete diff: для каждой touched issue — полный iter_worklogs_for_issue,
           чтобы не удалить ворклоги, не изменявшиеся в данном периоде.
        5. Bucket B (если teams задан) — остаётся как есть.
        """
        stats = UpdateStats()
        since_dt = datetime.combine(since, datetime.min.time())

        # Шаг 1+2: все изменённые ворклоги за период; группируем по issueId
        worklogs_by_issue: dict[str, list] = {}
        async for wl in self.jira.get_worklogs_updated_since(since_dt):
            await self._check_cancelled()
            worklogs_by_issue.setdefault(wl.issueId, []).append(wl)

        # Кеш lookup issue_id → local Issue
        issue_cache: dict[str, Optional[Issue]] = {}

        # Шаг 3: upsert для каждой touched issue, присутствующей в нашей БД
        for jira_issue_id, worklogs in worklogs_by_issue.items():
            local_issue = (
                self.db.query(Issue)
                .filter(Issue.jira_issue_id == jira_issue_id)
                .one_or_none()
            )
            issue_cache[jira_issue_id] = local_issue
            if local_issue is None:
                continue
            for wl in worklogs:
                author_schema = JiraUserSchema(
                    accountId=wl.author.accountId,
                    displayName=wl.author.displayName,
                    emailAddress=wl.author.emailAddress,
                    active=True,
                )
                employee = self._ensure_employee(author_schema)
                self._upsert_worklog(wl, local_issue.id, employee.id)
                stats.bucket_a_worklogs_upserted += 1
            stats.touched_issue_keys.add(jira_issue_id)

        # Шаг 4: delete diff — для каждой touched issue получаем полный список
        # ворклогов из Jira (чтобы не удалить старые, не изменявшиеся в периоде)
        for jira_issue_id in list(worklogs_by_issue.keys()):
            await self._check_cancelled()
            local_issue = issue_cache.get(jira_issue_id)
            if local_issue is None:
                continue
            all_jira_ids: set[str] = set()
            async for wl in self.jira.iter_worklogs_for_issue(jira_issue_id):
                all_jira_ids.add(wl.id)
            if all_jira_ids:
                stale_count = (
                    self.db.query(Worklog)
                    .filter(
                        Worklog.issue_id == local_issue.id,
                        ~Worklog.jira_worklog_id.in_(all_jira_ids),
                    )
                    .delete(synchronize_session=False)
                )
                stats.bucket_a_worklogs_deleted += stale_count
            self.db.commit()
            if on_progress is not None:
                await on_progress(stats, jira_issue_id)

        # ─── Ведро B ───
        if teams:
            await self._update_worklogs_bucket_b(
                since.isoformat(), teams, stats, on_progress,
            )

        return stats

    async def _update_worklogs_bucket_b(
        self,
        since_iso: str,
        teams: List[str],
        stats: "UpdateStats",
        on_progress: Optional[
            Callable[["UpdateStats", Optional[str]], Awaitable[None]]
        ] = None,
    ) -> None:
        """Employee-centric проход. Для каждого сотрудника из указанных
        команд — JQL по ``worklogAuthor``. Незнакомые issue создаём
        с ``out_of_scope=True``; их ворклоги от ЛЮБОГО автора (не только
        наших) попадают в БД, чтобы не разделять граф."""
        from app.models import EmployeeTeam

        # Собрать distinct сотрудников в этих командах
        emps = (
            self.db.query(Employee)
            .join(EmployeeTeam, EmployeeTeam.employee_id == Employee.id)
            .filter(EmployeeTeam.team.in_(teams))
            .distinct()
            .all()
        )
        # Dedup: одна задача может встретиться у нескольких сотрудников команды.
        # Delete diff применяем только при первом обходе задачи.
        seen_issues: set[str] = set()
        for emp in emps:
            await self._check_cancelled()
            jql = f'worklogAuthor = "{emp.jira_account_id}" AND updated >= "{since_iso}"'
            async for jira_issue in self.jira.iter_issues(
                jql,
                fields=["summary", "issuetype", "status", "project"],
                max_results=100,
            ):
                await self._check_cancelled()
                local = (
                    self.db.query(Issue)
                    .filter(Issue.jira_issue_id == jira_issue.id)
                    .one_or_none()
                )
                if local is None:
                    local = self._create_out_of_scope_issue(jira_issue)
                    stats.bucket_b_out_of_scope_created += 1
                stats.bucket_b_issues_scanned += 1
                jira_wl_ids_b: set[str] = set()
                async for wl in self.jira.iter_worklogs_for_issue(jira_issue.id):
                    await self._check_cancelled()
                    jira_wl_ids_b.add(wl.id)
                    author_schema = JiraUserSchema(
                        accountId=wl.author.accountId,
                        displayName=wl.author.displayName,
                        emailAddress=wl.author.emailAddress,
                        active=True,
                    )
                    employee = self._ensure_employee(author_schema)
                    self._upsert_worklog(wl, local.id, employee.id)
                    stats.bucket_b_worklogs_upserted += 1
                # Delete diff — только при первом обходе задачи
                if jira_wl_ids_b and jira_issue.id not in seen_issues:
                    local_wl_ids_b: set[str] = {
                        row[0]
                        for row in self.db.query(Worklog.jira_worklog_id).filter(
                            Worklog.issue_id == local.id
                        ).all()
                    }
                    stale_ids_b = local_wl_ids_b - jira_wl_ids_b
                    if stale_ids_b:
                        deleted_b = (
                            self.db.query(Worklog)
                            .filter(
                                Worklog.issue_id == local.id,
                                Worklog.jira_worklog_id.in_(stale_ids_b),
                            )
                            .delete(synchronize_session=False)
                        )
                        stats.bucket_b_worklogs_deleted += deleted_b
                seen_issues.add(jira_issue.id)
                stats.touched_issue_keys.add(jira_issue.key)
                self.db.commit()
                if on_progress is not None:
                    await on_progress(stats, jira_issue.key)

    def _create_out_of_scope_issue(self, jira_issue) -> "Issue":
        """Создать Issue с ``out_of_scope=True`` + автосоздать Project
        если его нет. Минимальный набор полей — summary/type/status/project."""
        proj_payload = jira_issue.fields.project
        project = (
            self.db.query(Project)
            .filter(Project.jira_project_id == proj_payload.id)
            .one_or_none()
        )
        if project is None:
            project = Project(
                jira_project_id=proj_payload.id,
                key=proj_payload.key,
                name=proj_payload.name,
                synced_at=datetime.utcnow(),
            )
            self.db.add(project)
            self.db.flush()

        status_obj = jira_issue.fields.status
        status_cat = None
        cat_obj = getattr(status_obj, "statusCategory", None)
        if cat_obj is not None:
            status_cat = getattr(cat_obj, "key", None)

        issue = Issue(
            jira_issue_id=jira_issue.id,
            key=jira_issue.key,
            project_id=project.id,
            summary=jira_issue.fields.summary,
            issue_type=jira_issue.fields.issuetype.name,
            status=status_obj.name,
            status_category=status_cat,
            out_of_scope=True,
            synced_at=datetime.utcnow(),
        )
        self.db.add(issue)
        self.db.flush()
        return issue
