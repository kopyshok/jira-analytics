"""ExecutiveSnapshot — кэш кросс-work-type дашборда руководителя."""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import generate_uuid


class ExecutiveSnapshot(Base):
    __tablename__ = "executive_dashboard_snapshots"
    __table_args__ = (
        UniqueConstraint("year", "quarter", "team_set_hash", name="uq_exec_snap_period_team"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    quarter: Mapped[int] = mapped_column(Integer, nullable=False)
    team_set_hash: Mapped[str] = mapped_column(String(32), nullable=False)
    team_set_json: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_data: Mapped[str] = mapped_column(Text, nullable=False)
    model_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    prompt_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    created_by: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )

    def __repr__(self) -> str:
        return f"<ExecutiveSnapshot {self.year}Q{self.quarter} team={self.team_set_hash[:8]}>"
