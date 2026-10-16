"""Консоль Jira и Confluence — запросы на чтение от имени сервера. Только администратор."""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth_deps import get_current_user
from app.database import get_db
from app.models.console_run import ConsoleRun
from app.models.user import User
from app.services import console_service

router = APIRouter()

KEEP_RUNS = 30


class RunIn(BaseModel):
    target: Literal["jira", "confluence"]
    text: str = Field(max_length=100_000)
    mask: bool = True


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat() + "Z"


def _first_line(text: str) -> str:
    for raw in text.splitlines():
        s = raw.strip()
        if s and not s.startswith("#"):
            return s
    return ""


def _brief(r: ConsoleRun) -> dict:
    return {
        "id": r.id,
        "created_at": _iso(r.created_at),
        "user_name": r.user_name,
        "target": r.target,
        "masked": r.masked,
        "first_line": _first_line(r.input_text),
        "request_count": r.request_count,
        "error_count": r.error_count,
        "rejected_count": r.rejected_count,
        "duration_ms": r.duration_ms,
    }


def _full(r: ConsoleRun) -> dict:
    return {**_brief(r), "input_text": r.input_text, "output_text": r.output_text}


def _prune(db: Session) -> None:
    """Оставить последние KEEP_RUNS запусков."""
    old = [
        row.id for row in db.query(ConsoleRun.id)
        .order_by(ConsoleRun.created_at.desc(), ConsoleRun.id.desc())
        .offset(KEEP_RUNS)
    ]
    if old:
        db.query(ConsoleRun).filter(ConsoleRun.id.in_(old)).delete(synchronize_session=False)
        db.commit()


@router.post("/run")
async def run(
    body: RunIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Выполнить строки и сохранить запуск в историю."""
    try:
        base, token = console_service.credentials(db, body.target)
        lines = console_service.parse_lines(body.text, base, body.target)
    except console_service.ConsoleError as e:
        raise HTTPException(status_code=400, detail=str(e))
    result = await console_service.execute(lines, body.target, body.mask, base, token)
    row = ConsoleRun(
        user_id=user.id,
        user_name=user.display_name or user.email,
        target=body.target,
        masked=body.mask,
        input_text=body.text,
        output_text=result.output,
        request_count=result.request_count,
        error_count=result.error_count,
        rejected_count=result.rejected_count,
        duration_ms=result.duration_ms,
    )
    db.add(row)
    db.commit()
    _prune(db)
    db.refresh(row)
    return _full(row)


@router.get("/runs")
def list_runs(db: Session = Depends(get_db)) -> dict:
    """Свежие запуски первыми, без текста результата."""
    rows = db.query(ConsoleRun).order_by(ConsoleRun.created_at.desc(), ConsoleRun.id.desc()).all()
    return {"items": [_brief(r) for r in rows]}


@router.get("/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db)) -> dict:
    row = db.get(ConsoleRun, run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Запуск не найден")
    return _full(row)


@router.delete("/runs/{run_id}", status_code=204)
def delete_run(run_id: str, db: Session = Depends(get_db)) -> None:
    row = db.get(ConsoleRun, run_id)
    if row:
        db.delete(row)
        db.commit()
