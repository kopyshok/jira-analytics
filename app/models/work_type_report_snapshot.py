"""WorkTypeReportSnapshot — full thematic report cache."""
from typing import Optional
from datetime import datetime, date
from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import generate_uuid


class WorkTypeReportSnapshot(Base):
    __tablename__ = "work_type_report_snapshots"
    __table_args__ = (UniqueConstraint("work_type_id", "year", "quarter", "month", "team_set_hash", name="uq_wt_report_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    work_type_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandatory_work_types.id", ondelete="CASCADE"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    quarter: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    team_set_hash: Mapped[str] = mapped_column(String(32), nullable=False)
    team_set_json: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_data: Mapped[str] = mapped_column(Text, nullable=False)
    dictionary_version: Mapped[int] = mapped_column(Integer, nullable=False)
    model_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    prompt_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    created_by: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
