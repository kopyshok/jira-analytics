"""Репозиторий SyncSchedule — CRUD расписания автозапуска pipeline."""

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.sync_schedule import SyncSchedule


class SyncScheduleRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_all(self) -> list[SyncSchedule]:
        return self.db.query(SyncSchedule).order_by(SyncSchedule.name).all()

    def get(self, schedule_id: str) -> Optional[SyncSchedule]:
        return self.db.get(SyncSchedule, schedule_id)

    def create(
        self,
        *,
        name: str,
        cron_expr: str,
        mode: str,
        team: Optional[str] = None,
        enabled: bool = True,
    ) -> SyncSchedule:
        item = SyncSchedule(
            name=name,
            cron_expr=cron_expr,
            mode=mode,
            team=team,
            enabled=enabled,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update(self, schedule_id: str, **fields) -> Optional[SyncSchedule]:
        item = self.db.get(SyncSchedule, schedule_id)
        if item is None:
            return None
        for k, v in fields.items():
            if hasattr(item, k):
                setattr(item, k, v)
        self.db.commit()
        return item

    def delete(self, schedule_id: str) -> bool:
        item = self.db.get(SyncSchedule, schedule_id)
        if item is None:
            return False
        self.db.delete(item)
        self.db.commit()
        return True

    def set_last_run(self, schedule_id: str, run_id: str, next_run_at: Optional[datetime]) -> None:
        item = self.db.get(SyncSchedule, schedule_id)
        if item is None:
            return
        item.last_run_id = run_id
        item.next_run_at = next_run_at
        self.db.commit()
