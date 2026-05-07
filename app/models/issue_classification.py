"""IssueClassification — Map-phase cache (per issue × work type)."""
from typing import Optional
from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class IssueClassification(Base, TimestampMixin):
    __tablename__ = "issue_classifications"
    __table_args__ = (UniqueConstraint("issue_id", "work_type_id", name="uq_classifications_issue_wt"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    issue_id: Mapped[str] = mapped_column(String(36), ForeignKey("issues.id", ondelete="CASCADE"), nullable=False)
    work_type_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandatory_work_types.id", ondelete="CASCADE"), nullable=False)
    theme_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("themes.id", ondelete="SET NULL"), nullable=True, index=True)
    candidate_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contribution_text: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    nature_tag: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    llm_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    model_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    prompt_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    dictionary_version: Mapped[int] = mapped_column(Integer, nullable=False)
    failed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failure_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    def __repr__(self) -> str:
        return f"<IssueClassification issue={self.issue_id} wt={self.work_type_id} theme={self.theme_id}>"
