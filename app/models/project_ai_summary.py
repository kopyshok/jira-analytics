"""ProjectAISummary — кэш AI-саммари по проекту (parent issue)."""
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import generate_uuid

if TYPE_CHECKING:
    from app.models.issue import Issue


class ProjectAISummary(Base):
    """AI-саммари проекта. Один на parent issue (UNIQUE issue_id).

    Заполняется фоновым job'ом или ручной кнопкой 'Обновить AI'.
    """

    __tablename__ = "project_ai_summaries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    issue_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("issues.id", ondelete="CASCADE"),
        unique=True, index=True, nullable=False,
    )
    goals_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_flow_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_checklist_json: Mapped[str] = mapped_column(Text, nullable=False)
    status_text: Mapped[str] = mapped_column(Text, nullable=False)
    workload_summary: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    model_used: Mapped[str] = mapped_column(String(64), nullable=False)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False,
    )

    issue: Mapped["Issue"] = relationship("Issue", lazy="joined")
