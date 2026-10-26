"""Страница «Переезд на новую Jira» (только администратор).

Пробный прогон, применение и повтор полной синхронизации — фоновые операции
в своём потоке (``runner``): ответ 202 сразу, ход — в ``GET`` (страница
опрашивает его, пока операция идёт).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.connectors.jira_client import JiraClient, JiraClientError
from app.core.auth_deps import require_admin
from app.database import get_db
from app.models.user import User
from app.services.jira_migration import overview, runner, store
from app.services.jira_migration.resolution import BLOCK_DONE, collect_blockers
from app.services.jira_migration.state import STATE_DONE, get_migration_state
from app.services.sync_lock import SyncLock

logger = logging.getLogger(__name__)
router = APIRouter()

DECISIONS_DONE = "Переезд уже выполнен — решения больше не меняются"
DECISIONS_BUSY = "Идёт операция переезда — решения можно менять после неё"
POST_CHECK_BUSY = "Идёт операция переезда — сверку можно запустить после её окончания"


class DecisionIn(BaseModel):
    kind: Literal["field", "issue", "person"]
    item_key: str
    decision: Optional[dict[str, Any]] = None


class ApplyIn(BaseModel):
    backup_confirmed: bool = False


class DcUserOut(BaseModel):
    key: str
    name: Optional[str] = None
    display_name: str
    email: Optional[str] = None
    active: bool


def _claim(db: Session, kind: str) -> runner.MigrationJob:
    """Занять слот фоновой операции; уже идёт другая — 409."""
    try:
        return runner.claim(db, kind)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("")
def get_overview(db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict[str, Any]:
    return overview.build_overview(db, now=datetime.utcnow())


@router.post("/dry-run", status_code=202)
def start_dry_run(db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict[str, Any]:
    if get_migration_state(db) == STATE_DONE:
        raise HTTPException(status_code=409, detail=BLOCK_DONE)
    job = _claim(db, runner.KIND_DRY_RUN)
    runner.start_dry_run(job)
    return overview.job_dict(job)


@router.put("/decisions")
def put_decision(
    body: DecisionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> dict[str, bool]:
    if get_migration_state(db) == STATE_DONE:
        raise HTTPException(status_code=409, detail=DECISIONS_DONE)
    if runner.is_running():
        raise HTTPException(status_code=409, detail=DECISIONS_BUSY)
    try:
        overview.check_decision_target(db, body.kind, body.item_key, body.decision)
        store.set_decision(db, body.kind, body.item_key, body.decision, user.display_name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True}


@router.get("/dc-users", response_model=list[DcUserOut])
async def search_dc_users(
    q: str = Query(..., min_length=2, max_length=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[DcUserOut]:
    """Поиск пользователя новой Jira по ФИО, логину или почте — для ручной привязки сотрудника.

    Неактивные учётки тоже: у уволенного сотрудника остались списания.
    Соединение с базой отпускается до обращения к Jira; поиск — без повторов:
    администратор ждёт ответа и может повторить сам.
    """
    try:
        jira = await run_in_threadpool(JiraClient.from_db, db)
        await run_in_threadpool(db.close)
        jira.max_retries = 1
        async with jira:
            users = await jira.search_users(q.strip(), max_results=20, include_inactive=True)
    except JiraClientError:
        logger.warning("Поиск пользователей новой Jira не удался", exc_info=True)
        raise HTTPException(status_code=502, detail=runner.JIRA_UNAVAILABLE) from None
    return [
        DcUserOut(
            key=u.jira_account_id, name=u.name, display_name=u.display_name, email=u.email,
            active=u.is_active,
        )
        for u in users
    ]


@router.post("/apply", status_code=202)
def start_apply(
    body: ApplyIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict[str, Any]:
    """Применение; после него в том же слоте — полная синхронизация всех ворклогов."""
    blockers = collect_blockers(
        db, now=datetime.utcnow(), backup_confirmed=body.backup_confirmed, job_running=runner.is_running(),
    )
    if blockers:
        raise HTTPException(status_code=409, detail="Нельзя применить: " + "; ".join(blockers))
    job = _claim(db, runner.KIND_APPLY)
    runner.start_apply(job, backup_confirmed=True)
    return overview.job_dict(job)


@router.post("/full-sync", status_code=202)
def restart_full_sync(db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict[str, Any]:
    """Повтор полной синхронизации со всеми ворклогами (если первая не стартовала, упала или прервана).

    Блокировка синка на прежнем запуске этого переезда не мешает: если он
    ещё идёт в этом процессе, слот операции занят (409), иначе он оборван
    перезапуском сервиса. Блокировка другого запуска — 409.
    """
    row = store.latest_report(db)
    if get_migration_state(db) != STATE_DONE or row is None or row.applied_at is None:
        raise HTTPException(status_code=409, detail=runner.FULL_SYNC_NOT_APPLIED)
    lock = SyncLock(db)
    holder = lock.current_run_id()
    if holder and holder != row.sync_run_id and not lock.is_stale():
        raise HTTPException(status_code=409, detail=runner.SYNC_BUSY)
    job = _claim(db, runner.KIND_FULL_SYNC)
    runner.start_full_sync_restart(job)
    return overview.job_dict(job)


@router.post("/post-check")
def run_post_check(db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict[str, Any]:
    """Сверка после: часы базы сейчас против новой Jira из отчёта. Сохраняется в отчёт.

    Пока идёт операция переезда (в том числе полная синхронизация), часы базы
    неполные — сверка отклоняется.
    """
    if runner.is_running():
        raise HTTPException(status_code=409, detail=POST_CHECK_BUSY)
    try:
        return runner.post_check_latest(db, now=datetime.utcnow())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
