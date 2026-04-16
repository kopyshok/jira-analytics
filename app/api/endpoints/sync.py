"""Sync API endpoints."""

from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.connectors.jira_client import JiraClient, JiraClientError, JiraAuthError
from app.services.sync_service import SyncService, SyncStats


router = APIRouter()


# === Request/Response schemas ===

class SyncRequest(BaseModel):
    """Request to start sync."""
    project_keys: Optional[List[str]] = None
    incremental: bool = True


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


class SyncStatusResponse(BaseModel):
    """Sync status from database."""
    entity: str
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
                user_name=user.displayName,
                user_email=user.emailAddress,
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
async def sync_projects(db: Session = Depends(get_db)):
    """Sync all projects from Jira.
    
    This is a lightweight operation that fetches project metadata only.
    Run this first before syncing issues.
    """
    try:
        async with JiraClient.from_db(db) as jira:
            service = SyncService(db, jira)
            count = await service.sync_projects()
            
            return SyncResponse(
                status="completed",
                message=f"Synced {count} projects",
                stats=service.stats.to_dict(),
            )
    except JiraClientError as e:
        raise HTTPException(status_code=502, detail=f"Jira error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/issues", response_model=SyncResponse)
async def sync_issues(
    request: SyncRequest = None,
    db: Session = Depends(get_db),
):
    """Sync issues from Jira.
    
    Args:
        project_keys: Optional list of project keys to sync.
                     If not provided, syncs all synced projects.
        incremental: If true, only sync issues updated since last sync.
    """
    request = request or SyncRequest()
    
    try:
        async with JiraClient.from_db(db) as jira:
            service = SyncService(db, jira)
            count = await service.sync_issues(
                project_keys=request.project_keys,
                incremental=request.incremental,
            )
            
            return SyncResponse(
                status="completed",
                message=f"Synced {count} issues",
                stats=service.stats.to_dict(),
            )
    except JiraClientError as e:
        raise HTTPException(status_code=502, detail=f"Jira error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/worklogs", response_model=SyncResponse)
async def sync_worklogs(db: Session = Depends(get_db)):
    """Sync worklogs for all synced issues.
    
    This can be a long-running operation depending on the number of issues.
    Consider running as background task for large datasets.
    """
    try:
        async with JiraClient.from_db(db) as jira:
            service = SyncService(db, jira)
            count = await service.sync_worklogs()
            
            return SyncResponse(
                status="completed",
                message=f"Synced {count} worklogs",
                stats=service.stats.to_dict(),
            )
    except JiraClientError as e:
        raise HTTPException(status_code=502, detail=f"Jira error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/comments", response_model=SyncResponse)
async def sync_comments(db: Session = Depends(get_db)):
    """Синхронизация комментариев к задачам из Jira."""
    try:
        async with JiraClient.from_db(db) as jira:
            service = SyncService(db, jira)
            count = await service.sync_comments()

            return SyncResponse(
                status="completed",
                message=f"Synced {count} comments",
                stats=service.stats.to_dict(),
            )
    except JiraClientError as e:
        raise HTTPException(status_code=502, detail=f"Jira error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/full", response_model=SyncResponse)
async def full_sync(
    request: SyncRequest = None,
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
    request = request or SyncRequest()
    
    if background and background_tasks:
        background_tasks.add_task(
            run_sync_task,
            db,
            request.project_keys,
            request.incremental,
        )
        return SyncResponse(
            status="started",
            message="Full sync started in background",
        )
    
    try:
        async with JiraClient.from_db(db) as jira:
            service = SyncService(db, jira)
            stats = await service.full_sync(
                project_keys=request.project_keys,
                incremental=request.incremental,
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
            last_sync=state.last_success_at.isoformat() if state.last_success_at else None,
            cursor=state.cursor_value,
            last_error=state.last_error,
        )
        for state in states
    ]
