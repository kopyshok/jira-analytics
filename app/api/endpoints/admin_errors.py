"""Последние ошибки сервера — только для администратора."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core import error_log
from app.database import get_db
from app.models.user import User

router = APIRouter()


@router.get("")
def list_errors(db: Session = Depends(get_db)) -> dict:
    """Свежие ошибки первыми + момент старта сервиса (виден перезапуск)."""
    items = error_log.snapshot()
    user_ids = {i["user_id"] for i in items if i.get("user_id")}
    names: dict[str, str] = {}
    if user_ids:
        names = {
            u.id: (u.display_name or u.email)
            for u in db.query(User).filter(User.id.in_(user_ids)).all()
        }
    return {
        "started_at": error_log.STARTED_AT.isoformat(),
        "capacity": error_log.MAX_RECORDS,
        "items": [{**i, "user": names.get(i.get("user_id") or "")} for i in items],
    }


@router.delete("", status_code=204)
def clear_errors() -> None:
    """Очистить список — после того как разобрались."""
    error_log.clear()
