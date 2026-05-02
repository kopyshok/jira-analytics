"""Settings API endpoints — manage Jira credentials via UI."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.app_setting import AppSetting
from app.connectors.jira_client import JiraClient, JiraClientError, JiraAuthError

router = APIRouter()


# --- Schemas ---

class JiraSettingsResponse(BaseModel):
    email: Optional[str] = None
    base_url: Optional[str] = None
    has_token: bool = False


class JiraSettingsUpdate(BaseModel):
    email: Optional[str] = None
    api_token: Optional[str] = None
    base_url: Optional[str] = None


class SettingUpdate(BaseModel):
    key: str
    value: Optional[str] = None


class JiraTestRequest(BaseModel):
    email: str
    api_token: str
    base_url: str


class JiraTestResponse(BaseModel):
    connected: bool
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    error: Optional[str] = None


# --- Helpers ---

def _get_setting(db: Session, key: str) -> Optional[str]:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else None


def _set_setting(db: Session, key: str, value: Optional[str]) -> None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))


LLM_KEYS = (
    "llm_provider",
    "llm_gemini_api_key",
    "llm_deepseek_api_key",
    "llm_anthropic_api_key",
    "llm_openai_api_key",
)


def _is_allowed_generic_key(key: str) -> bool:
    """Limit generic settings to non-secret UI/runtime keys."""
    if key in LLM_KEYS:
        return True
    return (
        key.startswith("ui_")
        or key == "worklog_reload_since_date"
        or (key.startswith("jira_") and key.endswith("_field_id"))
    )


# --- Endpoints ---

@router.get("/jira", response_model=JiraSettingsResponse)
async def get_jira_settings(db: Session = Depends(get_db)):
    """Получить сохранённые Jira-настройки (токен не возвращается)."""
    return JiraSettingsResponse(
        email=_get_setting(db, "jira_email"),
        base_url=_get_setting(db, "jira_base_url"),
        has_token=_get_setting(db, "jira_api_token") is not None,
    )


@router.put("/jira", response_model=JiraSettingsResponse)
async def save_jira_settings(
    body: JiraSettingsUpdate,
    db: Session = Depends(get_db),
):
    """Сохранить Jira-настройки в БД."""
    if body.email is not None:
        _set_setting(db, "jira_email", body.email)
    if body.api_token is not None:
        _set_setting(db, "jira_api_token", body.api_token)
    if body.base_url is not None:
        _set_setting(db, "jira_base_url", body.base_url)
    db.commit()

    return JiraSettingsResponse(
        email=_get_setting(db, "jira_email"),
        base_url=_get_setting(db, "jira_base_url"),
        has_token=_get_setting(db, "jira_api_token") is not None,
    )


@router.put("/generic")
async def save_generic_setting(body: SettingUpdate, db: Session = Depends(get_db)):
    """Сохранить произвольную настройку (key → value)."""
    if not _is_allowed_generic_key(body.key):
        raise HTTPException(status_code=403, detail="Setting key is not allowed")
    _set_setting(db, body.key, body.value)
    db.commit()
    return {"key": body.key, "ok": True}


@router.get("/generic/{key}")
async def get_generic_setting(key: str, db: Session = Depends(get_db)):
    """Прочитать произвольную настройку по ключу."""
    if not _is_allowed_generic_key(key):
        raise HTTPException(status_code=403, detail="Setting key is not allowed")
    return {"key": key, "value": _get_setting(db, key)}


@router.post("/jira/test", response_model=JiraTestResponse)
async def test_jira_credentials(body: JiraTestRequest):
    """Проверить подключение к Jira с указанными credentials (без сохранения)."""
    try:
        async with JiraClient(
            base_url=body.base_url,
            email=body.email,
            api_token=body.api_token,
        ) as jira:
            user = await jira.get_myself()
            return JiraTestResponse(
                connected=True,
                user_name=user.display_name,
                user_email=user.email,
            )
    except JiraAuthError as e:
        return JiraTestResponse(connected=False, error=f"Ошибка аутентификации: {e}")
    except JiraClientError as e:
        return JiraTestResponse(connected=False, error=str(e))
