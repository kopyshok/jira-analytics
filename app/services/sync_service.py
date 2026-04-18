"""Sync service - orchestrates Jira data synchronization."""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional, List, Tuple, Any
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


logger = logging.getLogger("jira_analytics.sync")

# Sentinel, чтобы отличать «поле не передано» от «поле передано с пустым значением».
# None как «пусто» теперь валидный сигнал «очистить в БД».
_UNSET: Any = object()


@dataclass
class ReloadStats:
    """Результат жёсткой перезагрузки worklog'ов по дате начала."""

    deleted: int = 0
    issues_scanned: int = 0
    worklogs_inserted: int = 0


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
    
    def __init__(self, db: Session, jira_client: JiraClient):
        self.db = db
        self.jira = jira_client
        self.stats = SyncStats()
        
        # Initialize repositories
        self.employee_repo = BaseRepository(Employee, db)
        self.project_repo = BaseRepository(Project, db)
        self.issue_repo = BaseRepository(Issue, db)
        self.worklog_repo = BaseRepository(Worklog, db)
        self.comment_repo = BaseRepository(Comment, db)
        self.sync_state_repo = BaseRepository(SyncState, db)
        self.scope_project_repo = BaseRepository(ScopeProject, db)
    
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
            "jira_account_id": jira_user.accountId,
            "display_name": jira_user.displayName,
            "email": jira_user.emailAddress,
            "is_active": jira_user.active,
            "avatar_url": jira_user.avatar_48,
            "synced_at": datetime.utcnow(),
        }
        return self.employee_repo.upsert_by_field(
            "jira_account_id",
            jira_user.accountId,
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
    ) -> Tuple[Issue, bool]:
        """Upsert issue from Jira.

        ``team`` / ``participating_teams`` / ``goals`` принимают ``_UNSET``
        чтобы означать «колонку не трогать». Явный ``None`` / ``[]`` / ``""``
        от вызывающего — это «очистить значение в БД» (когда поле
        очищено в Jira).
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

        count = 0
        unresolved_parents: List[Tuple[str, str]] = []  # (child_issue_id, parent_key)
        async for jira_issue in self.jira.get_issues_updated_since(
            project_keys=keys,
            since=since,
            extra_fields=extra_fields,
        ):
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
                jira_issue, project.id, parent_id, **extra_kwargs,
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
        base_fields = [
            "summary", "description", "issuetype", "status",
            "priority", "project", "parent", "creator",
            "assignee", "created", "updated",
            "statuscategorychangedate",
        ]
        fields = base_fields + list(extra_fields)

        BATCH = 100
        matched = 0
        total = len(jira_keys)
        logger.info(f"Refreshing {total} issues by key (batch={BATCH})")

        for i in range(0, total, BATCH):
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
                    jira_issue, project.id, parent_id, **extra_kwargs,
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
            "statuscategorychangedate",
        ]
        request_fields = base_fields + list(extra_fields)

        projects_jql = ", ".join(f'"{k}"' for k in scope_keys)

        report: dict = {}
        for team in teams:
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
                        jira_issue, project.id, parent_id, **extra_kwargs,
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

    def reload_worklogs_since(self, since: date) -> ReloadStats:
        """Удаляет worklog'и с ``started_at >= since`` и перечитывает их
        из Jira по JQL ``worklogDate >= since``.

        Перебирает только те issue, что уже есть в локальной БД: незнакомые
        пропускаются, чтобы не расширять scope молча. Не трогает
        ``sync_state.last_sync``.
        """
        import asyncio

        since_dt = datetime.combine(since, datetime.min.time())
        deleted = (
            self.db.query(Worklog)
            .filter(Worklog.started_at >= since_dt)
            .delete(synchronize_session=False)
        )
        self.db.commit()

        stats = ReloadStats(deleted=deleted)
        jql = f'worklogDate >= "{since.isoformat()}"'

        async def run() -> None:
            async for jira_issue in self.jira.iter_issues(
                jql,
                fields=["summary", "issuetype", "status", "project"],
                max_results=100,
            ):
                local = (
                    self.db.query(Issue)
                    .filter(Issue.jira_issue_id == jira_issue.id)
                    .one_or_none()
                )
                if local is None:
                    continue
                stats.issues_scanned += 1
                async for wl in self.jira.iter_worklogs_for_issue(jira_issue.id):
                    started = self._normalize_worklog_started(wl.started)
                    if started is None or started < since_dt:
                        continue
                    employee = self._ensure_employee_from_worklog_author(wl.author)
                    inserted = self._upsert_worklog_from_reload(wl, local, employee, started)
                    if inserted:
                        stats.worklogs_inserted += 1
                self.db.commit()

        asyncio.run(run())
        return stats

    @staticmethod
    def _normalize_worklog_started(raw: Any) -> Optional[datetime]:
        """Привести ``started`` из Jira к naive UTC ``datetime``.

        Принимает либо готовый ``datetime`` (aware/naive), либо ISO-строку.
        """
        if raw is None:
            return None
        if isinstance(raw, datetime):
            if raw.tzinfo is not None:
                return raw.astimezone(timezone.utc).replace(tzinfo=None)
            return raw
        if isinstance(raw, str):
            return _parse_jira_datetime(raw)
        return None

    def _ensure_employee_from_worklog_author(self, author: Any) -> Employee:
        """Найти/создать сотрудника по автору worklog'а.

        Работает со схемой ``JiraWorklogAuthorSchema`` (camelCase) и с её
        snake_case формой (mock в тестах). Поиск идёт по ``jira_account_id``;
        если сотрудника нет — создаём.
        """
        def _pick_str(*names: str) -> Optional[str]:
            for name in names:
                val = getattr(author, name, None)
                if isinstance(val, str):
                    return val
            return None

        account_id = _pick_str("account_id", "accountId")
        display_name = _pick_str("display_name", "displayName")
        email = _pick_str("email_address", "emailAddress")
        active_raw = getattr(author, "active", True)
        active = bool(active_raw) if isinstance(active_raw, bool) else True

        existing = self.employee_repo.get_by_field("jira_account_id", account_id)
        if existing:
            return existing
        data = {
            "jira_account_id": account_id,
            "display_name": display_name,
            "email": email,
            "is_active": active,
            "synced_at": datetime.utcnow(),
        }
        return self.employee_repo.create(data)

    def _upsert_worklog_from_reload(
        self,
        wl: Any,
        issue: Issue,
        employee: Employee,
        started_at: datetime,
    ) -> bool:
        """Upsert worklog при reload; возвращает True если строка создана."""
        seconds: int = 0
        for name in ("time_spent_seconds", "timeSpentSeconds"):
            val = getattr(wl, name, None)
            if isinstance(val, int):
                seconds = val
                break
        hours = seconds / 3600 if seconds else 0.0
        comment_raw = getattr(wl, "comment", None)
        comment_text = comment_raw if isinstance(comment_raw, (str, type(None))) else None
        worklog_id = getattr(wl, "id", None)
        if not isinstance(worklog_id, str):
            worklog_id = str(worklog_id)

        data = {
            "jira_worklog_id": worklog_id,
            "started_at": started_at,
            "hours": hours,
            "time_spent_seconds": seconds,
            "comment_text": comment_text,
            "issue_id": issue.id,
            "employee_id": employee.id,
            "synced_at": datetime.utcnow(),
        }
        _, inserted = self.worklog_repo.upsert_by_field(
            "jira_worklog_id", worklog_id, data,
        )
        return inserted
