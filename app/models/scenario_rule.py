"""ScenarioRule — per-scenario mandatory-work percentage rule."""
from typing import Optional
from sqlalchemy import Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import TimestampMixin, generate_uuid
from app.database import Base


class ScenarioRule(Base, TimestampMixin):
    __tablename__ = "scenario_rules"
    __table_args__ = (
        UniqueConstraint("scenario_id", "role", "work_type_id",
                         name="uq_scenario_rule_scope"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("planning_scenarios.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    role: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # NULL = для всех ролей
    work_type_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("mandatory_work_types.id"), nullable=False,
    )
    percent_of_norm: Mapped[float] = mapped_column(Float, nullable=False)
