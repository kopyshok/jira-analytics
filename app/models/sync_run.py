"""SyncRun model — история запусков pipeline синхронизации."""

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, ForeignKey, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class SyncRun(Base, TimestampMixin):
    """Запуск sync pipeline — manual или scheduled.

    `stages_json` хранит список словарей вида
    `{stage, started, finished, status, counts, error}`.
    """

    __tablename__ = "sync_run"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    # running | ok | partial | failed | cancelled | skipped
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)
    # manual | scheduled
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    # quick | normal | full | team
    team: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    stages_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    error_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    schedule_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("sync_schedule.id", ondelete="SET NULL"), nullable=True
    )

    def __repr__(self) -> str:
        return f"<SyncRun {self.id} {self.mode} {self.status}>"
