"""SyncLock — advisory lock через AppSetting.

Хранит JSON {run_id, started_at}. Stale lock (старше TTL) считается
свободным. Single-process, single-user MVP.
"""

import json
from datetime import datetime, timedelta
from typing import Optional

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

    def _payload(self) -> Optional[dict]:
        row = self._row()
        if row is None or row.value is None or row.value == "":
            return None
        try:
            return json.loads(row.value)
        except Exception:
            return None

    def current_run_id(self) -> Optional[str]:
        payload = self._payload()
        return payload.get("run_id") if payload else None

    def is_stale(self) -> bool:
        payload = self._payload()
        if not payload:
            return False
        started = datetime.fromisoformat(payload["started_at"])
        return datetime.utcnow() - started > self.stale_after

    def acquire(self, run_id: str) -> bool:
        if self.current_run_id() and not self.is_stale():
            return False
        self._write({"run_id": run_id, "started_at": datetime.utcnow().isoformat()})
        return True

    def release(self) -> None:
        self._write(None)

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
