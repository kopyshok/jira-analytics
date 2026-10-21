"""Объединение двойников сотрудников — только для администратора."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

import uuid

from app.database import get_db
from app.services import employee_merge
from app.services.sync_lock import SyncLock

router = APIRouter()


class MergeRequest(BaseModel):
    keep_id: str
    drop_id: str


@router.get("/suggestions")
def suggestions(db: Session = Depends(get_db)) -> list[dict]:
    """Похожие карточки (одинаковые фамилия и имя) — кандидаты на объединение."""
    return employee_merge.suggestions(db)


@router.get("/preview")
def preview(
    keep_id: str = Query(...), drop_id: str = Query(...), db: Session = Depends(get_db),
) -> dict:
    """Что переедет на правильную карточку и что мешает объединению."""
    try:
        return employee_merge.preview(db, keep_id, drop_id)
    except employee_merge.MergeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.post("")
def merge(req: MergeRequest, db: Session = Depends(get_db)) -> dict:
    """Влить лишнюю карточку в правильную.

    На время объединения берётся блокировка синхронизации: запуск, прочитавший
    учётки до объединения, иначе записал бы часы на удаляемую карточку.
    """
    lock = SyncLock(db)
    run_id = f"employee-merge-{uuid.uuid4()}"
    if not lock.acquire(run_id):
        raise HTTPException(
            status_code=409, detail="Идёт синхронизация — объедините карточки после её окончания.",
        )
    try:
        result = employee_merge.merge(db, req.keep_id, req.drop_id)
        db.commit()
    except employee_merge.MergeError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except Exception:
        db.rollback()
        raise
    finally:
        lock.release(run_id)
    return result
