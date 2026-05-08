"""UI config — глобальные настройки видимости разделов меню.

GET — для всех залогиненных (SideMenu читает на каждом рендере).
PUT — только admin (управление через /settings).

Хранится в AppSetting.value как JSON-массив маршрутов, например ["/executive"].
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth_deps import get_current_user, require_admin
from app.database import get_db
from app.models.app_setting import AppSetting
from app.models.user import User

router = APIRouter()

_KEY = "ui_hidden_section_keys"


class HiddenSectionsResponse(BaseModel):
    keys: list[str]


class HiddenSectionsUpdate(BaseModel):
    keys: list[str]


def _read(db: Session) -> list[str]:
    row = db.query(AppSetting).filter(AppSetting.key == _KEY).first()
    if not row or not row.value:
        return []
    try:
        v = json.loads(row.value)
    except json.JSONDecodeError:
        return []
    return [str(x) for x in v if isinstance(x, str)]


def _write(db: Session, keys: list[str]) -> None:
    cleaned = sorted({k.strip() for k in keys if isinstance(k, str) and k.strip()})
    payload = json.dumps(cleaned, ensure_ascii=False)
    row = db.query(AppSetting).filter(AppSetting.key == _KEY).first()
    if row:
        row.value = payload
    else:
        db.add(AppSetting(key=_KEY, value=payload))


@router.get("/hidden-sections", response_model=HiddenSectionsResponse)
def get_hidden_sections(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Прочитать список скрытых маршрутов (любой залогиненный)."""
    return HiddenSectionsResponse(keys=_read(db))


@router.put("/hidden-sections", response_model=HiddenSectionsResponse)
def put_hidden_sections(
    body: HiddenSectionsUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Обновить список скрытых маршрутов (admin only)."""
    if any(not isinstance(k, str) for k in body.keys):
        raise HTTPException(status_code=422, detail="keys must be list of strings")
    _write(db, body.keys)
    db.commit()
    return HiddenSectionsResponse(keys=_read(db))
