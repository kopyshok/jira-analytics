"""Админ-эндпоинты выгрузки базы в переносимый SQLite-файл."""
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.auth_deps import require_admin
from app.models.user import User
from app.services import db_snapshot_service as snapshot

router = APIRouter()


class ExportStatus(BaseModel):
    state: str
    tables_total: int
    tables_done: int
    current_table: str | None = None
    rows_copied: int
    error: str | None = None
    file_name: str | None = None
    file_size: int | None = None
    local_password: str | None = None
    revision: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


def _to_status(job: snapshot.ExportJob) -> ExportStatus:
    return ExportStatus(
        state=job.state,
        tables_total=job.tables_total,
        tables_done=job.tables_done,
        current_table=job.current_table,
        rows_copied=job.rows_copied,
        error=job.error,
        file_name=job.file_name if job.file_path else None,
        file_size=job.file_size if job.file_path else None,
        local_password=job.local_password if job.file_path else None,
        revision=job.revision,
        started_at=job.started_at.isoformat() if job.started_at else None,
        finished_at=job.finished_at.isoformat() if job.finished_at else None,
    )


@router.get("", response_model=ExportStatus)
def get_status(_: User = Depends(require_admin)) -> ExportStatus:
    return _to_status(snapshot.current_job())


@router.post("", response_model=ExportStatus, status_code=202)
def start_export(
    background_tasks: BackgroundTasks,
    _: User = Depends(require_admin),
) -> ExportStatus:
    if snapshot.is_running():
        raise HTTPException(status_code=409, detail="Выгрузка уже выполняется")
    background_tasks.add_task(snapshot.build_snapshot)
    return ExportStatus(state="running", tables_total=0, tables_done=0, rows_copied=0)


@router.get("/download")
def download(_: User = Depends(require_admin)) -> FileResponse:
    job = snapshot.current_job()
    if job.state != "done" or not job.file_path or not Path(job.file_path).exists():
        raise HTTPException(status_code=404, detail="Готовой выгрузки нет")
    return FileResponse(
        job.file_path,
        media_type="application/gzip",
        filename=job.file_name or "snapshot.db.gz",
    )
