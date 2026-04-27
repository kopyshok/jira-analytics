"""Репозиторий SyncRun — CRUD истории запусков pipeline."""

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.sync_run import SyncRun


class SyncRunRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        mode: str,
        trigger: str,
        team: Optional[str] = None,
        schedule_id: Optional[str] = None,
    ) -> SyncRun:
        run = SyncRun(
            started_at=datetime.utcnow(),
            status="running",
            trigger=trigger,
            mode=mode,
            team=team,
            schedule_id=schedule_id,
            stages_json=[],
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def finalize(
        self,
        run_id: str,
        *,
        status: str,
        stages: list,
        error_text: Optional[str] = None,
    ) -> None:
        run = self.db.get(SyncRun, run_id)
        if run is None:
            return
        run.finished_at = datetime.utcnow()
        run.status = status
        run.stages_json = stages
        run.error_text = error_text
        self.db.commit()

    def list_latest(self, limit: int = 20) -> list[SyncRun]:
        return (
            self.db.query(SyncRun)
            .order_by(SyncRun.started_at.desc())
            .limit(limit)
            .all()
        )

    def get(self, run_id: str) -> Optional[SyncRun]:
        return self.db.get(SyncRun, run_id)

    def latest_successful_finished_at(self) -> Optional[datetime]:
        run = (
            self.db.query(SyncRun)
            .filter(SyncRun.status.in_(("ok", "partial")))
            .order_by(SyncRun.finished_at.desc())
            .first()
        )
        return run.finished_at if run else None
