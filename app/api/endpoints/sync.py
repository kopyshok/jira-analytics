"""Sync API endpoints."""

import asyncio
from datetime import date
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.connectors.jira_client import JiraClient, JiraClientError, JiraAuthError
from app.services.sync_service import SyncService, SyncStats


router = APIRouter()


def _disconnect_checker(request: Optional[Request]):
    """Коллбек для SyncService: None если request отсутствует (unit-тесты),
    иначе полёт в ``request.is_disconnected()`` на каждом вызове.

    Используется для cancel-по-клиенту: при обрыве HTTP-соединения SyncService
    поднимает ``CancelledError`` и эндпоинт отдаёт 499.
    """
    if request is None:
        return None

    async def _check() -> bool:
        return await request.is_disconnected()

    return _check


# HTTP 499 — nginx-овый код "Client Closed Request". Используем его же
# для консистентного ответа на отмену пользователем.
CLIENT_CLOSED_REQUEST = 499

# Отдельный роутер для браузинга пользователей Jira — монтируется в
# ``app.api.router`` под префиксом ``/jira`` (чтобы URL был
# ``/api/v1/jira/users/search`` без ``/sync``).
jira_router = APIRouter()


# === Request/Response schemas ===

class SyncRequest(BaseModel):
    """Request to start sync."""
    project_keys: Optional[List[str]] = None
    incremental: bool = True


class RefreshIssuesRequest(BaseModel):
    """Точечная синхронизация по списку ключей Jira."""
    jira_keys: List[str]


class SyncTeamsRequest(BaseModel):
    """Синхронизация задач по списку продуктовых команд."""
    teams: List[str]


class SyncResponse(BaseModel):
    """Sync operation response."""
    status: str
    message: str
    stats: Optional[dict] = None


class ConnectionTestResponse(BaseModel):
    """Connection test response."""
    connected: bool
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    error: Optional[str] = None


class WorklogReloadRequest(BaseModel):
    """Запрос на жёсткую перезагрузку worklog'ов с указанной даты."""
    since: date


class WorklogReloadResponse(BaseModel):
    """Результат перезагрузки worklog'ов."""
    deleted: int
    issues_scanned: int
    worklogs_inserted: int


class SyncStatusResponse(BaseModel):
    """Sync status from database.

    ``scope`` is empty ``""`` for the global per-entity cursor and carries
    the team name for per-team cursors (written by ``POST /sync/teams``).
    """
    entity: str
    scope: str = ""
    last_sync: Optional[str] = None
    cursor: Optional[str] = None
    last_error: Optional[str] = None


class JiraProjectItem(BaseModel):
    """Проект Jira для browse-списка."""
    id: str
    key: str
    name: str
    project_type: Optional[str] = None
    in_scope: bool = False


class JiraEpicItem(BaseModel):
    """Эпик/задача из Jira для browse-списка."""
    key: str
    summary: str
    issue_type: str
    status: str


# === Background task for async sync ===

async def run_sync_task(
    db: Session,
    project_keys: Optional[List[str]] = None,
    incremental: bool = True,
):
    """Background task to run full sync."""
    try:
        async with JiraClient.from_db(db) as jira:
            service = SyncService(db, jira)
            await service.full_sync(
                project_keys=project_keys,
                incremental=incremental,
            )
    except Exception as e:
        # Log error - in production, store in SyncState
        import logging
        logging.error(f"Sync task failed: {e}")


# === Endpoints ===

@router.get("/test-connection", response_model=ConnectionTestResponse)
async def test_jira_connection(db: Session = Depends(get_db)):
    """Test connection to Jira Cloud.

    Verifies that:
    - Jira credentials are configured
    - API token is valid
    - User has access
    """
    try:
        async with JiraClient.from_db(db) as jira:
            user = await jira.get_myself()
            return ConnectionTestResponse(
                connected=True,
                user_name=user.display_name,
                user_email=user.email,
            )
    except JiraAuthError as e:
        return ConnectionTestResponse(
            connected=False,
            error=f"Authentication failed: {e}",
        )
    except JiraClientError as e:
        return ConnectionTestResponse(
            connected=False,
            error=str(e),
        )


@router.post("/projects", response_model=SyncResponse)
async def sync_projects(http_request: Request, db: Session = Depends(get_db)):
    """Sync all projects from Jira.

    This is a lightweight operation that fetches project metadata only.
    Run this first before syncing issues.
    """
    try:
        async with JiraClient.from_db(db) as jira:
            service = SyncService(db, jira, cancel_check=_disconnect_checker(http_request))
            count = await service.sync_projects()

            return SyncResponse(
                status="completed",
                message=f"Synced {count} projects",
                stats=service.stats.to_dict(),
            )
    except asyncio.CancelledError:
        raise HTTPException(status_code=CLIENT_CLOSED_REQUEST, detail="Sync cancelled by client")
    except JiraClientError as e:
        raise HTTPException(status_code=502, detail=f"Jira error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/issues", response_model=SyncResponse)
async def sync_issues(
    http_request: Request,
    body: SyncRequest = None,
    db: Session = Depends(get_db),
):
    """Sync issues from Jira.

    Args:
        project_keys: Optional list of project keys to sync.
                     If not provided, syncs all synced projects.
        incremental: If true, only sync issues updated since last sync.
    """
    body = body or SyncRequest()

    try:
        async with JiraClient.from_db(db) as jira:
            service = SyncService(db, jira, cancel_check=_disconnect_checker(http_request))
            count = await service.sync_issues(
                project_keys=body.project_keys,
                incremental=body.incremental,
            )

            return SyncResponse(
                status="completed",
                message=f"Synced {count} issues",
                stats=service.stats.to_dict(),
            )
    except asyncio.CancelledError:
        raise HTTPException(status_code=CLIENT_CLOSED_REQUEST, detail="Sync cancelled by client")
    except JiraClientError as e:
        raise HTTPException(status_code=502, detail=f"Jira error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/issues/refresh", response_model=SyncResponse)
async def refresh_issues(
    body: RefreshIssuesRequest,
    http_request: Request,
    db: Session = Depends(get_db),
):
    """Перечитать с Jira конкретные задачи по ключам.

    Обновляет только те задачи, что уже существуют локально; новые не
    создаёт. Нужно чтобы дотащить новое поле (``status_changed_at`` и т.п.)
    на текущий видимый набор задач без полной пересинхронизации.
    """
    if not body.jira_keys:
        return SyncResponse(status="noop", message="Список ключей пуст")

    try:
        async with JiraClient.from_db(db) as jira:
            service = SyncService(db, jira, cancel_check=_disconnect_checker(http_request))
            matched, total = await service.refresh_issues_by_keys(body.jira_keys)
            return SyncResponse(
                status="completed",
                message=f"Обновлено {matched} из {total} задач",
                stats={"matched": matched, "requested": total},
            )
    except asyncio.CancelledError:
        raise HTTPException(status_code=CLIENT_CLOSED_REQUEST, detail="Sync cancelled by client")
    except JiraClientError as e:
        raise HTTPException(status_code=502, detail=f"Jira error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/teams", response_model=SyncResponse)
async def sync_teams(
    body: SyncTeamsRequest,
    http_request: Request,
    db: Session = Depends(get_db),
):
    """Быстрая синхронизация новых/изменённых задач выбранных команд.

    Для каждой команды ведётся отдельный курсор в ``sync_state
    (entity_name="issues", scope=<team>)``. На вход — список названий
    команд (значения team-поля Jira). Курсор двигается только при
    успехе; ошибка по одной команде не ломает остальные.
    """
    if not request.teams:
        return SyncResponse(status="noop", message="Список команд пуст")

    try:
        async with JiraClient.from_db(db) as jira:
            service = SyncService(db, jira, cancel_check=_disconnect_checker(http_request))
            report = await service.sync_team_issues(body.teams)
            total_matched = sum(int(r.get("matched", 0)) for r in report.values())
            total_created = sum(int(r.get("created", 0)) for r in report.values())
            errors = {t: r["error"] for t, r in report.items() if r.get("error")}
            if errors:
                summary = (
                    f"Команд синхронизировано с ошибками: {len(errors)}. "
                    f"Всего задач обновлено: {total_matched}, создано: {total_created}."
                )
            else:
                summary = (
                    f"Команд синхронизировано: {len(report)}. "
                    f"Задач обновлено: {total_matched}, создано: {total_created}."
                )
            return SyncResponse(
                status="completed",
                message=summary,
                stats={"per_team": report},
            )
    except asyncio.CancelledError:
        raise HTTPException(status_code=CLIENT_CLOSED_REQUEST, detail="Sync cancelled by client")
    except JiraClientError as e:
        raise HTTPException(status_code=502, detail=f"Jira error: {e}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/worklogs", response_model=SyncResponse)
async def sync_worklogs(http_request: Request, db: Session = Depends(get_db)):
    """Sync worklogs for all synced issues.

    This can be a long-running operation depending on the number of issues.
    Consider running as background task for large datasets.
    """
    try:
        async with JiraClient.from_db(db) as jira:
            service = SyncService(db, jira, cancel_check=_disconnect_checker(http_request))
            count = await service.sync_worklogs()

            return SyncResponse(
                status="completed",
                message=f"Synced {count} worklogs",
                stats=service.stats.to_dict(),
            )
    except asyncio.CancelledError:
        raise HTTPException(status_code=CLIENT_CLOSED_REQUEST, detail="Sync cancelled by client")
    except JiraClientError as e:
        raise HTTPException(status_code=502, detail=f"Jira error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/worklogs/reload", response_model=WorklogReloadResponse)
async def reload_worklogs(
    req: WorklogReloadRequest,
    http_request: Request,
    db: Session = Depends(get_db),
):
    """Жёсткая перезагрузка worklog'ов с указанной даты по ``started_at``.

    Удаляет все записи, у которых ``started_at >= since`` и перечитывает их
    из Jira через JQL ``worklogDate >= since``. Сохраняет дату в AppSetting
    ``worklog_reload_since_date``.
    """
    from app.api.endpoints.settings import _set_setting

    try:
        async with JiraClient.from_db(db) as jira:
            service = SyncService(db, jira, cancel_check=_disconnect_checker(http_request))
            stats = await service.reload_worklogs_since(req.since)
    except asyncio.CancelledError:
        raise HTTPException(status_code=CLIENT_CLOSED_REQUEST, detail="Sync cancelled by client")
    except JiraClientError as e:
        raise HTTPException(status_code=502, detail=f"Jira error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    _set_setting(db, "worklog_reload_since_date", req.since.isoformat())
    db.commit()

    return WorklogReloadResponse(
        deleted=stats.deleted,
        issues_scanned=stats.issues_scanned,
        worklogs_inserted=stats.worklogs_inserted,
    )


@router.post("/comments", response_model=SyncResponse)
async def sync_comments(http_request: Request, db: Session = Depends(get_db)):
    """Синхронизация комментариев к задачам из Jira."""
    try:
        async with JiraClient.from_db(db) as jira:
            service = SyncService(db, jira, cancel_check=_disconnect_checker(http_request))
            count = await service.sync_comments()

            return SyncResponse(
                status="completed",
                message=f"Synced {count} comments",
                stats=service.stats.to_dict(),
            )
    except asyncio.CancelledError:
        raise HTTPException(status_code=CLIENT_CLOSED_REQUEST, detail="Sync cancelled by client")
    except JiraClientError as e:
        raise HTTPException(status_code=502, detail=f"Jira error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/full", response_model=SyncResponse)
async def full_sync(
    http_request: Request,
    body: SyncRequest = None,
    background: bool = False,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
):
    """Run full sync: projects -> issues -> worklogs.
    
    Args:
        project_keys: Optional list of project keys to sync.
        incremental: If true, only sync data updated since last sync.
        background: If true, run sync as background task.
    """
    body = body or SyncRequest()

    if background and background_tasks:
        background_tasks.add_task(
            run_sync_task,
            db,
            body.project_keys,
            body.incremental,
        )
        return SyncResponse(
            status="started",
            message="Full sync started in background",
        )

    try:
        async with JiraClient.from_db(db) as jira:
            service = SyncService(db, jira, cancel_check=_disconnect_checker(http_request))
            stats = await service.full_sync(
                project_keys=body.project_keys,
                incremental=body.incremental,
            )

        # Auto-recalculate mappings after full sync
        from app.services.mapping_service import MappingService
        mapping_svc = MappingService(db)
        mapping_svc.recalculate_all()

        return SyncResponse(
            status="completed",
            message=f"Full sync completed in {stats.duration_seconds:.1f}s",
            stats=stats.to_dict(),
        )
    except asyncio.CancelledError:
        raise HTTPException(status_code=CLIENT_CLOSED_REQUEST, detail="Sync cancelled by client")
    except JiraClientError as e:
        raise HTTPException(status_code=502, detail=f"Jira error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jira-projects", response_model=List[JiraProjectItem])
async def browse_jira_projects(
    search: Optional[str] = None,
    team: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Список проектов из Jira Cloud для выбора в scope.

    Возвращает все проекты с флагом ``in_scope`` — уже добавлен в scope или нет.
    Опциональный ``search`` фильтрует по key/name (case-insensitive).
    Опциональный ``team`` фильтрует проекты по задачам с этой командой.
    """
    from app.models import ScopeProject
    from app.models.app_setting import AppSetting

    try:
        async with JiraClient.from_db(db) as jira:
            scope_keys: set[str] = {
                sp.jira_project_key
                for sp in db.query(ScopeProject).all()
            }

            # If team filter is specified, we will probe each project separately
            # (matches both "product team" and "participating teams" fields via OR).
            # Сканирование всех задач команды неприемлемо по времени — при ORDER BY
            # project ASC лимит перебором выедается задачами одного проекта.
            team_field_ids: list[str] = []
            if team:
                product_row = db.query(AppSetting).filter(AppSetting.key == "jira_team_field_id").first()
                participating_row = db.query(AppSetting).filter(AppSetting.key == "jira_participating_teams_field_id").first()
                team_field_ids = [r.value for r in (product_row, participating_row) if r and r.value]

            async def project_has_team(project_key: str) -> bool:
                if not team or not team_field_ids:
                    return True
                clauses = " OR ".join(f'"{fid}" = "{team}"' for fid in team_field_ids)
                jql = f'project = "{project_key}" AND ({clauses})'
                response = await jira.search_issues(
                    jql=jql,
                    max_results=1,
                    fields=["summary", "issuetype", "status", "project"],
                )
                return len(response.issues) > 0

            projects: list[JiraProjectItem] = []
            async for p in jira.iter_projects(max_results=50):
                if search:
                    q = search.lower()
                    if q not in p.key.lower() and q not in p.name.lower():
                        continue
                if team and team_field_ids and not await project_has_team(p.key):
                    continue
                projects.append(JiraProjectItem(
                    id=p.id,
                    key=p.key,
                    name=p.name,
                    project_type=p.projectTypeKey,
                    in_scope=p.key in scope_keys,
                ))

            projects.sort(key=lambda x: x.key)
            return projects
    except JiraClientError as e:
        raise HTTPException(status_code=502, detail=f"Jira error: {e}")


@router.get("/jira-epics", response_model=List[JiraEpicItem])
async def browse_jira_epics(
    project_key: str,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Эпики и верхнеуровневые задачи проекта из Jira.

    Отдаёт задачи типа Epic + задачи без parent (потенциальные корни).
    ``search`` фильтрует по summary (case-insensitive).
    """
    try:
        async with JiraClient.from_db(db) as jira:
            jql = (
                f'project = "{project_key}" '
                f'AND (issuetype = Epic OR "Parent Link" is EMPTY) '
                f"ORDER BY key ASC"
            )
            items: list[JiraEpicItem] = []
            async for issue in jira.iter_issues(jql=jql, max_results=100):
                summary = issue.fields.summary
                if search and search.lower() not in summary.lower():
                    continue
                items.append(JiraEpicItem(
                    key=issue.key,
                    summary=summary,
                    issue_type=issue.fields.issuetype.name,
                    status=issue.fields.status.name,
                ))
            return items
    except JiraClientError as e:
        raise HTTPException(status_code=502, detail=f"Jira error: {e}")


class JiraFieldItem(BaseModel):
    """Поле Jira для выбора в настройках."""
    id: str
    name: str
    custom: bool = False


@router.get("/jira-fields", response_model=List[JiraFieldItem])
async def browse_jira_fields(db: Session = Depends(get_db)):
    """Список полей Jira (включая кастомные) для настройки team-поля."""
    try:
        async with JiraClient.from_db(db) as jira:
            fields = await jira.get_fields()
            return [
                JiraFieldItem(
                    id=f["id"],
                    name=f.get("name", f["id"]),
                    custom=f.get("custom", False),
                )
                for f in fields
            ]
    except JiraClientError as e:
        raise HTTPException(status_code=502, detail=f"Jira error: {e}")


@router.get("/jira-issuetypes", response_model=List[str])
async def browse_jira_issuetypes(db: Session = Depends(get_db)):
    """Уникальные имена типов задач из Jira (каталог issuetype).

    Используется фронтом для выпадающих списков в настройках (например,
    Правила иерархии). Если в Jira несколько контекстов одного типа с тем
    же именем — схлопываем по имени, чтобы список соответствовал
    ``Issue.issue_type`` (в БД хранится имя).
    """
    try:
        async with JiraClient.from_db(db) as jira:
            types = await jira.get_issue_types()
            names: set[str] = set()
            for t in types:
                name = t.get("name")
                if name:
                    names.add(name)
            return sorted(names)
    except JiraClientError as e:
        raise HTTPException(status_code=502, detail=f"Jira error: {e}")


@router.get("/jira-teams", response_model=List[str])
async def browse_jira_teams(db: Session = Depends(get_db)):
    """Уникальные значения полей 'Продуктовая команда' и 'Участвующие команды' из Jira.

    Использует настройки ``jira_team_field_id`` и
    ``jira_participating_teams_field_id`` — объединяет значения из обоих полей.
    """
    from app.models.app_setting import AppSetting

    rows = (
        db.query(AppSetting)
        .filter(AppSetting.key.in_(("jira_team_field_id", "jira_participating_teams_field_id")))
        .all()
    )
    field_ids = [r.value for r in rows if r.value]
    if not field_ids:
        raise HTTPException(
            status_code=400,
            detail="Поля команды не настроены. Укажите jira_team_field_id и/или jira_participating_teams_field_id.",
        )

    try:
        async with JiraClient.from_db(db) as jira:
            merged: set[str] = set()
            for fid in field_ids:
                values = await jira.get_field_distinct_values(fid)
                merged.update(values)
            return sorted(merged)
    except JiraClientError as e:
        raise HTTPException(status_code=502, detail=f"Jira error: {e}")


@router.get("/status", response_model=List[SyncStatusResponse])
async def get_sync_status(db: Session = Depends(get_db)):
    """Get sync status for all entities."""
    from app.models import SyncState

    states = db.query(SyncState).all()

    return [
        SyncStatusResponse(
            entity=state.entity_name,
            scope=state.scope or "",
            last_sync=state.last_success_at.isoformat() if state.last_success_at else None,
            cursor=state.cursor_value,
            last_error=state.last_error,
        )
        for state in states
    ]


# === /jira/users/search (jira_router) ===


class JiraUserResponse(BaseModel):
    jira_account_id: str
    display_name: str
    email: Optional[str] = None
    is_active: bool
    avatar_url: Optional[str] = None


@jira_router.get("/users/search", response_model=List[JiraUserResponse])
async def search_jira_users(
    query: str = Query(..., min_length=2),
    db: Session = Depends(get_db),
):
    """Поиск пользователей Jira по подстроке (минимум 2 символа).

    Возвращает до 20 совпадений без записи в БД.
    """
    async with JiraClient.from_db(db) as jira:
        users = await jira.search_users(query, max_results=20)
    return [
        JiraUserResponse(
            jira_account_id=u.jira_account_id,
            display_name=u.display_name,
            email=u.email,
            is_active=u.is_active,
            avatar_url=u.avatar_url,
        )
        for u in users
    ]
