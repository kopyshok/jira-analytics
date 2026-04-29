"""ScenarioRulesSnapshot — снимок scenario_rules (правил обязательных работ) на момент утверждения."""
from typing import Optional, TYPE_CHECKING
from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.scenario_revision import ScenarioRevision


class ScenarioRulesSnapshot(Base, TimestampMixin):
    __tablename__ = "scenario_rules_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenario_revisions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    role: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    work_type_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    work_type_label: Mapped[str] = mapped_column(String(255), nullable=False)
    pct_of_norm: Mapped[float] = mapped_column(Float, nullable=False)

    revision: Mapped["ScenarioRevision"] = relationship(back_populates="rules_snapshots")
