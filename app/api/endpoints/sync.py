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


# === Background task for async sync ===

async def run_sync_task(
    db: Session,
    project_keys: Optional[List[str]] = None,
    incremental: bool = True,
):
    """Background task to run full sync."""
    try:
        async with JiraClient() as jira:
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
async def test_jira_connection():
    """Test connection to Jira Cloud.
    
    Verifies that:
    - Jira credentials are configured
    - API token is valid
    - User has access
    """
    try:
        async with JiraClient() as jira:
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
        async with JiraClient() as jira:
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
        async with JiraClient() as jira:
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
        async with JiraClient() as jira:
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
        async with JiraClient() as jira:
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
        async with JiraClient() as jira:
            service = SyncService(db, jira)
            stats = await service.full_sync(
                project_keys=request.project_keys,
                incremental=request.incremental,
            )
            
            return SyncResponse(
                status="completed",
                message=f"Full sync completed in {stats.duration_seconds:.1f}s",
                stats=stats.to_dict(),
            )
    except JiraClientError as e:
        raise HTTPException(status_code=502, detail=f"Jira error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
