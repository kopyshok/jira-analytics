"""ScenarioAllocationSnapshot — копия allocation вместе с атрибутами backlog_item на момент утверждения."""
from typing import Optional, TYPE_CHECKING
from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import expression
from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.scenario_revision import ScenarioRevision


class ScenarioAllocationSnapshot(Base, TimestampMixin):
    __tablename__ = "scenario_allocation_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenario_revisions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    allocation_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    backlog_item_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    sort_order: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    included_flag: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=expression.true()
    )
    involvement_coefficient: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    issue_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    customer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cost_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    impact: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    risk: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    priority: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    estimate_analyst_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    estimate_dev_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    estimate_qa_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    estimate_opo_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    override_estimate_analyst_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    override_estimate_dev_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    override_estimate_qa_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    override_estimate_opo_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    opo_analyst_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    assignee_employee_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    assignee_role_at_approval: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    revision: Mapped["ScenarioRevision"] = relationship(back_populates="allocation_snapshots")
