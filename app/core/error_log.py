"""Кольцевой буфер последних ошибок сервера — источник для админской страницы.

Живёт в памяти процесса, а не в БД намеренно: самый частый сбой, который тут
разбирают, — недоступная база, и записать такую ошибку в неё невозможно.

ponytail: история теряется при перезапуске сервиса и видна только текущему
процессу. Если приложение поедет в несколько воркеров или понадобится архив
за прошлые запуски — сюда придёт таблица или внешний сборщик логов.
"""
from __future__ import annotations

import traceback
import uuid
from collections import deque
from datetime import datetime
from typing import Any

MAX_RECORDS = 200
MAX_TRACEBACK_CHARS = 8000

_records: deque[dict[str, Any]] = deque(maxlen=MAX_RECORDS)

#: Момент старта процесса — по нему на странице видно, перезапускался ли сервис.
STARTED_AT = datetime.now().astimezone()


def _user_id_from(request: Any) -> str | None:
    """Достать пользователя из токена, не трогая БД: она может быть недоступна."""
    from app.config import get_settings
    from app.core.security import decode_access_token

    try:
        header = request.headers.get("authorization") or ""
        token = header[7:] if header.lower().startswith("bearer ") else None
        token = token or request.cookies.get(get_settings().auth_cookie_name)
        if not token:
            return None
        return decode_access_token(token).get("sub")
    except Exception:
        return None


def record(request: Any, exc: BaseException) -> str:
    """Запомнить ошибку. Возвращает короткий номер для показа пользователю."""
    entry_id = uuid.uuid4().hex[:12]
    _records.appendleft(
        {
            "id": entry_id,
            "at": datetime.now().astimezone().isoformat(),
            "method": request.method,
            "path": request.url.path,
            "query": str(request.url.query or ""),
            "error_type": type(exc).__name__,
            "message": str(exc)[:500],
            "traceback": "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            )[-MAX_TRACEBACK_CHARS:],
            "user_id": _user_id_from(request),
        }
    )
    return entry_id


def snapshot() -> list[dict[str, Any]]:
    """Копия буфера, свежие записи первыми."""
    return list(_records)


def clear() -> None:
    _records.clear()
