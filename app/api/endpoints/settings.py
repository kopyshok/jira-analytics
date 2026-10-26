"""Settings API endpoints — manage Jira credentials via UI."""

import re
import httpx
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.app_setting import AppSetting
from app.models.sync_state import SyncState
from app.connectors.jira_client import JiraClient, JiraClientError, JiraAuthError
from app.connectors.confluence_client import ConfluenceClient, ConfluenceClientError
from app.services.plan_sources import PLAN_HOURS_SETTING_KEYS, field_layout, parse_field_setting
from app.services.jira_migration.fields import FIELD_SETTING_RE
from app.services.jira_migration.state import STATE_DONE, get_migration_state
from app.services.token_renewal import renewal_status, state_key

router = APIRouter()

FIELDS_LOCKED_MESSAGE = "Поля Jira настраиваются на странице переезда, пока переезд не завершён"


def _with_scheme(base_url: str) -> str:
    """Достроить схему адресу Jira, если её не указали.

    Без схемы ссылки на задачи в разделе KPI (и везде, где base_url
    используется для формирования ``.../browse/KEY``) получались
    относительными и вели в никуда.
    """
    trimmed = base_url.strip()
    if trimmed and not re.match(r"^https?://", trimmed, re.IGNORECASE):
        return f"https://{trimmed}"
    return trimmed


# --- Schemas ---

class JiraSettingsResponse(BaseModel):
    base_url: Optional[str] = None
    has_token: bool = False


class JiraSettingsUpdate(BaseModel):
    api_token: Optional[str] = None
    base_url: Optional[str] = None


class SettingUpdate(BaseModel):
    key: str
    value: Optional[str] = None


class JiraTestRequest(BaseModel):
    api_token: str
    base_url: str


class JiraTestResponse(BaseModel):
    connected: bool
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    error: Optional[str] = None


class ConfluenceSettingsResponse(BaseModel):
    base_url: Optional[str] = None
    has_token: bool = False


class ConfluenceSettingsUpdate(BaseModel):
    base_url: Optional[str] = None
    api_token: Optional[str] = None


class ConfluenceTestResponse(BaseModel):
    connected: bool
    user_name: Optional[str] = None
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
    "llm_gemini_model",
    "llm_openrouter_api_key",
    "llm_openrouter_model",
    "llm_openrouter_fallback_models",
    "llm_deepseek_api_key",
    "llm_deepseek_model",
    "llm_omniroute_base_url",
    "llm_omniroute_api_key",
    "llm_omniroute_model",
    "llm_anthropic_api_key",
    "llm_openai_api_key",
    "llm_project_summary_system_prompt",
)


def _is_allowed_generic_key(key: str) -> bool:
    """Limit generic settings to non-secret UI/runtime keys."""
    if key in LLM_KEYS:
        return True
    if key in ("ai_enabled", "planning_multi_team_by_epics", "planning_opo_cutoff"):
        return True
    # Даты вкладки «Синхронизация → Дополнительно» отдаёт GET /sync/reload-dates:
    # вкладка открыта всем, а этот роутер — только администратору.
    return key.startswith("ui_") or (key.startswith("jira_") and key.endswith("_field_id"))


# --- Endpoints ---

def _jira_settings(db: Session) -> JiraSettingsResponse:
    return JiraSettingsResponse(
        base_url=_get_setting(db, "jira_base_url"),
        has_token=_get_setting(db, "jira_api_token") is not None,
    )


@router.get("/jira", response_model=JiraSettingsResponse)
def get_jira_settings(db: Session = Depends(get_db)):
    """Получить сохранённые Jira-настройки (токен не возвращается)."""
    return _jira_settings(db)


@router.put("/jira", response_model=JiraSettingsResponse)
def save_jira_settings(
    body: JiraSettingsUpdate,
    db: Session = Depends(get_db),
):
    """Сохранить адрес Jira и персональный токен в БД."""
    if body.api_token is not None:
        _set_setting(db, "jira_api_token", body.api_token.strip())
        # Срок вставленного вручную токена неизвестен — самопродление начнёт заново.
        _set_setting(db, state_key("jira"), None)
    if body.base_url is not None:
        _set_setting(db, "jira_base_url", _with_scheme(body.base_url))
    db.commit()
    return _jira_settings(db)


def _check_plan_hours_fields(db: Session, key: str, value: Optional[str]) -> None:
    """Поля оценки роли: мусорный список не сохраняем, смена полей, их вида
    или порядка — перечитать все задачи при следующем синке (одни названия
    не в счёт).

    Синк задач берёт из Jira только изменённые с прошлого раза. Без сброса
    курсора у старых задач не появились бы значения новых полей и споры.
    """
    new_specs = parse_field_setting(value)
    if value and value.strip().startswith("[") and not new_specs:
        raise HTTPException(
            status_code=422, detail="В списке полей оценки нет ни одного поля Jira",
        )
    if field_layout(_get_setting(db, key)) != field_layout(value):
        for state in db.query(SyncState).filter(SyncState.entity_name == "issues"):
            state.last_success_at = None


@router.put("/generic")
def save_generic_setting(body: SettingUpdate, db: Session = Depends(get_db)):
    """Сохранить произвольную настройку (key → value)."""
    if not _is_allowed_generic_key(body.key):
        raise HTTPException(status_code=403, detail="Setting key is not allowed")
    if FIELD_SETTING_RE.match(body.key) and get_migration_state(db) != STATE_DONE:
        # Применение переезда перепишет поля из снимка облачных настроек: правка здесь потерялась бы.
        raise HTTPException(status_code=409, detail=FIELDS_LOCKED_MESSAGE)
    if body.key in PLAN_HOURS_SETTING_KEYS:
        _check_plan_hours_fields(db, body.key, body.value)
    _set_setting(db, body.key, body.value)
    db.commit()
    return {"key": body.key, "ok": True}


@router.get("/generic/{key}")
def get_generic_setting(key: str, db: Session = Depends(get_db)):
    """Прочитать произвольную настройку по ключу."""
    if not _is_allowed_generic_key(key):
        raise HTTPException(status_code=403, detail="Setting key is not allowed")
    return {"key": key, "value": _get_setting(db, key)}


@router.post("/jira/test", response_model=JiraTestResponse)
async def test_jira_credentials(body: JiraTestRequest):
    """Проверить подключение к Jira с указанными credentials (без сохранения)."""
    # Пустой токен клиент подменил бы токеном из .env и отправил его
    # на присланный адрес.
    if not body.api_token.strip():
        raise HTTPException(status_code=400, detail="Укажите персональный токен Jira")
    try:
        async with JiraClient(
            base_url=_with_scheme(body.base_url),
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


@router.get("/token-renewal")
def get_token_renewal(db: Session = Depends(get_db)):
    """Самопродление токенов Jira и Confluence: включено ли, до какого числа ключ, последняя ошибка."""
    return renewal_status(db)


def _confluence_settings(db: Session) -> ConfluenceSettingsResponse:
    return ConfluenceSettingsResponse(
        base_url=_get_setting(db, "confluence_base_url"),
        has_token=_get_setting(db, "confluence_api_token") is not None,
    )


@router.get("/confluence", response_model=ConfluenceSettingsResponse)
def get_confluence_settings(db: Session = Depends(get_db)):
    """Адрес Confluence и признак сохранённого токена (сам токен не отдаём)."""
    return _confluence_settings(db)


@router.put("/confluence", response_model=ConfluenceSettingsResponse)
def save_confluence_settings(
    body: ConfluenceSettingsUpdate,
    db: Session = Depends(get_db),
):
    """Сохранить адрес Confluence и персональный токен."""
    if body.base_url is not None:
        _set_setting(db, "confluence_base_url", _with_scheme(body.base_url))
    if body.api_token is not None:
        _set_setting(db, "confluence_api_token", body.api_token.strip())
        _set_setting(db, state_key("confluence"), None)
    db.commit()
    return _confluence_settings(db)


@router.post("/confluence/test", response_model=ConfluenceTestResponse)
async def test_confluence_connection(db: Session = Depends(get_db)):
    """Проверить подключение к Confluence с сохранёнными адресом и токеном."""
    try:
        confluence = await run_in_threadpool(ConfluenceClient.from_db, db)
        async with confluence as client:
            user = await client.get_current_user()
    except ConfluenceClientError as e:
        return ConfluenceTestResponse(connected=False, error=str(e))
    except httpx.HTTPError as e:
        return ConfluenceTestResponse(connected=False, error=f"Нет связи с Confluence: {e}")
    return ConfluenceTestResponse(
        connected=True,
        user_name=user.get("displayName") or user.get("username"),
    )
