"""SyncLock — advisory lock через AppSetting.

Хранит JSON {run_id, started_at}. Stale lock (старше TTL) считается
свободным. Взятие, продление и снятие своей блокировки — условной записью
по прежнему значению: из двух одновременных запусков блокировку получает один.
"""

import json
from datetime import datetime, timedelta
from typing import Any, Optional, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.app_setting import AppSetting

KEY = "sync_lock"
DEFAULT_STALE_AFTER_MIN = 60


class SyncLock:
    def __init__(self, db: Session, stale_after_minutes: int = DEFAULT_STALE_AFTER_MIN) -> None:
        self.db = db
        self.stale_after = timedelta(minutes=stale_after_minutes)

    def _row(self) -> Optional[AppSetting]:
        return self.db.query(AppSetting).filter(AppSetting.key == KEY).one_or_none()

    def _raw(self) -> tuple[bool, Optional[str]]:
        """(строка есть, значение) — колонкой, мимо объектов сессии: всегда из базы."""
        row = self.db.execute(select(AppSetting.value).where(AppSetting.key == KEY)).first()
        return (True, row[0]) if row is not None else (False, None)

    @staticmethod
    def _parse(raw: Optional[str]) -> Optional[dict]:
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    def _payload(self) -> Optional[dict]:
        return self._parse(self._raw()[1])

    def _stale(self, payload: dict) -> bool:
        started = datetime.fromisoformat(payload["started_at"])
        return datetime.utcnow() - started > self.stale_after

    def current_run_id(self) -> Optional[str]:
        payload = self._payload()
        return payload.get("run_id") if payload else None

    def is_stale(self) -> bool:
        payload = self._payload()
        return bool(payload) and self._stale(cast(dict, payload))

    def _swap(self, old: Optional[str], new: Optional[str]) -> bool:
        """Записать ``new``, только если в базе всё ещё ``old``. Коммитит."""
        current = AppSetting.value.is_(None) if old is None else AppSetting.value == old
        result = self.db.execute(
            update(AppSetting)
            .where(AppSetting.key == KEY, current)
            .values(value=new)
            .execution_options(synchronize_session=False)
        )
        self.db.commit()
        return (cast(CursorResult[Any], result).rowcount or 0) == 1

    def acquire(self, run_id: str, *, replacing: Optional[str] = None) -> bool:
        """Взять блокировку, если она свободна или зависла. Коммитит.

        ``replacing`` — запуск, который заведомо не идёт (сервис перезапустился
        посреди него): его блокировка считается свободной и без зависания.
        Запись условная (по прочитанному значению): если между чтением и
        записью блокировку взял другой запуск — отказ. Строки ещё нет и её
        одновременно создал другой — повтор уже как обновление.
        """
        for _ in range(2):
            exists, raw = self._raw()
            payload = self._parse(raw)
            holder = payload.get("run_id") if payload else None
            if holder and holder != replacing and not self._stale(cast(dict, payload)):
                return False
            new = json.dumps({"run_id": run_id, "started_at": datetime.utcnow().isoformat()})
            if exists:
                return self._swap(raw, new)
            try:
                self.db.add(AppSetting(key=KEY, value=new))
                self.db.commit()
                return True
            except IntegrityError:
                self.db.rollback()
        return False

    def heartbeat(self, run_id: str) -> bool:
        """Продлевает свою блокировку: долгий прогон не должен считаться зависшим.

        ``False`` — блокировка не наша (снята или её забрал другой запуск);
        чужую не трогает. Коммитит сессию.
        """
        raw = self._raw()[1]
        payload = self._parse(raw)
        if not payload or payload.get("run_id") != run_id:
            return False
        payload["started_at"] = datetime.utcnow().isoformat()
        return self._swap(raw, json.dumps(payload))

    def release(self, run_id: Optional[str] = None) -> None:
        """Снять блокировку. С ``run_id`` — только свою: чужую, взятую после
        зависания нашей, не трогать."""
        if run_id is None:
            self._write(None)
            return
        raw = self._raw()[1]
        payload = self._parse(raw)
        if payload and payload.get("run_id") == run_id:
            self._swap(raw, None)

    def _write(self, payload: Optional[dict]) -> None:
        row = self._row()
        value = json.dumps(payload) if payload else None
        if row is None:
            row = AppSetting(key=KEY, value=value)
            self.db.add(row)
        else:
            row.value = value
        self.db.commit()

    def _set_started_at(self, started_at: datetime) -> None:
        # Helper for tests
        payload = self._payload() or {}
        payload["started_at"] = started_at.isoformat()
        self._write(payload)
