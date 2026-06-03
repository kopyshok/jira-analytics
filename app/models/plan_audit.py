"""PlanAudit — журнал правок плановых часов задачи.

См. spec docs/superpowers/specs/2026-06-03-rfa-epic-hierarchy-design.md (раздел «Хранение»).
Источники (source):
  - jira_sync — изменение пришло из Jira (без активной ручной правки)
  - jira_sync_conflict — изменение из Jira, но есть ручная правка (требует PM-решения)
  - manual_edit — ручная правка PM через UI/API
  - manual_revert — откат к Jira-значению или к точке истории
  - conflict_accepted — PM принял Jira-значение, _manual обнулён
  - conflict_ignored — PM проигнорировал, _manual сохранён
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import generate_uuid


class PlanAudit(Base):
    __tablename__ = "plan_audit"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    issue_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("issues.id", ondelete="CASCADE"), nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    value_before: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    value_after: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
