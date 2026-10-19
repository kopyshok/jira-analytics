"""Самопродление персональных токенов Jira и Confluence.

СБ ограничила срок персонального токена 14 днями. Раз в час сервис смотрит,
сколько осталось жить токену, и за неделю до конца (или сразу, если срок
неизвестен — токен вставлен вручную) выпускает текущим токеном новый,
проверяет его и переключается. Свой прежний токен отзывает через сутки —
синхронизация, начатая на нём, успевает закончиться. Токен, вставленный
вручную, не отзывается: Jira не говорит, какой это из токенов пользователя, —
он истечёт сам.

Работает только при ``TOKEN_AUTO_RENEW=true`` (включено в серверном образе):
копия базы на другом компьютере иначе выпустила бы свой токен и отозвала
токен рабочего сервера.

Состояние — JSON в AppSetting ``<система>_token_renewal``:
``id``, ``expires_at``, ``renewed_at``, ``prev_id``, ``replaced_at``, ``error``, ``error_at``.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.app_setting import AppSetting

logger = logging.getLogger(__name__)

TOKEN_DAYS = 14
RENEW_WHEN_LEFT = timedelta(days=7)
REVOKE_PREVIOUS_AFTER = timedelta(days=1)
TOKEN_NAME = "Jira Analytics — автопродление"
PAT_PATH = "/rest/pat/latest/tokens"
TIMEOUT = httpx.Timeout(30.0, connect=15.0)

#: система → (ключ адреса, ключ токена, запрос проверки токена)
SYSTEMS = {
    "jira": ("jira_base_url", "jira_api_token", "/rest/api/2/myself"),
    "confluence": ("confluence_base_url", "confluence_api_token", "/rest/api/user/current"),
}

_DATETIME: TypeAdapter[datetime] = TypeAdapter(datetime)


class RenewalError(Exception):
    """Продлить не удалось; текст показывается администратору."""


def state_key(system: str) -> str:
    return f"{system}_token_renewal"


def _get(db: Session, key: str) -> Optional[str]:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else None


def _set(db: Session, key: str, value: Optional[str]) -> None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value  # type: ignore[assignment]  # колонка допускает NULL
    else:
        db.add(AppSetting(key=key, value=value))


def load_state(db: Session, system: str) -> dict[str, Any]:
    """Состояние продления системы; нет записи или мусор — пустое."""
    raw = _get(db, state_key(system))
    try:
        data = json.loads(raw) if raw else {}
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _parse_dt(value: Any) -> Optional[datetime]:
    """Дата из ответа Jira (``+0300`` и ``+03:00``) или из состояния, в UTC; мусор — None."""
    if not value:
        return None
    try:
        dt = _DATETIME.validate_python(value)
    except ValidationError:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "X-Atlassian-Token": "no-check",
    }


def _failure(what: str, resp: httpx.Response) -> RenewalError:
    """Ошибка шага с кодом ответа и коротким текстом (страница вместо данных — без текста)."""
    detail = resp.text.strip()[:200]
    if detail.startswith("<"):
        detail = ""
    return RenewalError(f"{what}: ответ {resp.status_code}" + (f" — {detail}" if detail else ""))


async def _revoke_quietly(client: httpx.AsyncClient, token: str, token_id: Any) -> bool:
    """Отозвать токен по номеру; сбой — только в журнал. True — отозван или его уже нет."""
    if not token_id:
        return False
    try:
        resp = await client.delete(f"{PAT_PATH}/{token_id}", headers=_headers(token))
    except httpx.HTTPError as exc:
        logger.warning("token renewal: токен %s не отозван: %s", token_id, type(exc).__name__)
        return False
    if resp.is_success or resp.status_code == 404:
        return True
    logger.warning("token renewal: токен %s не отозван, ответ %s", token_id, resp.status_code)
    return False


async def _revoke_previous(
    client: httpx.AsyncClient, token: str, state: dict[str, Any], now: datetime,
) -> None:
    """Отозвать свой прежний токен через сутки после замены; сбой — повтор на следующей проверке."""
    prev_id = state.get("prev_id")
    replaced_at = _parse_dt(state.get("replaced_at"))
    if not prev_id or (replaced_at and now - replaced_at < REVOKE_PREVIOUS_AFTER):
        return
    if await _revoke_quietly(client, token, prev_id):
        state.pop("prev_id", None)
        state.pop("replaced_at", None)


async def _issue(
    client: httpx.AsyncClient, token: str, check_path: str, state: dict[str, Any], now: datetime,
) -> str:
    """Выпустить текущим токеном новый, проверить его, записать в состояние; вернуть новый."""
    resp = await client.post(
        PAT_PATH, headers=_headers(token),
        json={"name": TOKEN_NAME, "expirationDuration": TOKEN_DAYS},
    )
    if not resp.is_success:
        raise _failure("выпуск нового ключа", resp)
    data = resp.json()
    new_token = data.get("rawToken") if isinstance(data, dict) else None
    if not new_token:
        raise RenewalError("выпуск нового ключа: в ответе нет ключа")
    try:
        check = await client.get(check_path, headers=_headers(new_token))
        if check.status_code != 200:
            raise _failure("проверка нового ключа", check)
    except (RenewalError, httpx.HTTPError):
        # Непроверенный ключ остался бы жить в Jira (лимит — 10 токенов): отзываем текущим.
        await _revoke_quietly(client, token, data.get("id"))
        raise
    if state.get("id"):
        state["prev_id"] = state["id"]
        state["replaced_at"] = now.isoformat()
    expires = _parse_dt(data.get("expiringAt")) or now + timedelta(days=TOKEN_DAYS)
    state.update(id=data.get("id"), expires_at=expires.isoformat(), renewed_at=now.isoformat())
    return new_token


async def renew_system(db: Session, system: str, now: Optional[datetime] = None) -> None:
    """Проверить токен системы и продлить, если срок неизвестен или до конца ≤ 7 дней."""
    now = now or datetime.now(timezone.utc)
    url_key, token_key, check_path = SYSTEMS[system]
    base_url, token = _get(db, url_key), _get(db, token_key)
    if not (base_url and token):
        return
    state = load_state(db, system)
    error: Optional[str] = None
    new_token: Optional[str] = None
    try:
        async with httpx.AsyncClient(
            base_url=base_url.rstrip("/"), timeout=TIMEOUT, follow_redirects=False,
        ) as client:
            try:
                await _revoke_previous(client, token, state, now)
                expires = _parse_dt(state.get("expires_at"))
                if expires is None or expires - now <= RENEW_WHEN_LEFT:
                    new_token = await _issue(client, token, check_path, state, now)
            except RenewalError as exc:
                error = str(exc)
            except httpx.HTTPError as exc:
                error = f"нет связи с сервером ({type(exc).__name__})"
            except ValueError:
                error = "сервер ответил не данными — проверьте адрес"
            # Администратор мог вставить свой ключ, пока мы ждали Jira: его ключ главнее.
            db.expire_all()
            if _get(db, token_key) != token:
                if new_token:
                    await _revoke_quietly(client, token, state.get("id"))
                logger.info("token renewal %s: ключ заменён вручную во время продления — результат отброшен", system)
                return
    except httpx.HTTPError as exc:  # сбой при закрытии клиента
        error = error or f"нет связи с сервером ({type(exc).__name__})"
    if new_token:
        _set(db, token_key, new_token)
    if error:
        state.update(error=error, error_at=now.isoformat())
        logger.warning("token renewal %s: %s", system, error)
    else:
        state.pop("error", None)
        state.pop("error_at", None)
    _set(db, state_key(system), json.dumps(state, ensure_ascii=False))
    db.commit()


async def renew_tokens_job() -> None:
    """Задание планировщика: продлить токены Jira и Confluence, если включено на этом сервере."""
    if not get_settings().token_auto_renew:
        return
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        for system in SYSTEMS:
            try:
                await renew_system(db, system)
            except Exception:
                logger.exception("token renewal %s: сбой", system)
                db.rollback()
    finally:
        db.close()


def renewal_status(db: Session) -> dict[str, Any]:
    """Состояние продления для настроек и плашки администратора; без токена — ``None``."""
    result: dict[str, Any] = {"enabled": get_settings().token_auto_renew}
    for system, (_, token_key, _) in SYSTEMS.items():
        if not _get(db, token_key):
            result[system] = None
            continue
        state = load_state(db, system)
        result[system] = {k: state.get(k) for k in ("expires_at", "renewed_at", "error", "error_at")}
    return result
