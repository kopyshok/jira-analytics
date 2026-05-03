"""ResourcePlan — план расписания для квартала/команды."""

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.planning_scenario import PlanningScenario
    from app.models.resource_plan_assignment import ResourcePlanAssignment
    from app.models.plan_item_dependency import PlanItemDependency
    from app.models.plan_conflict import PlanConflict


class ResourcePlan(Base, TimestampMixin):
    """Ресурсный план квартала.

    status: draft | computing | ready | stale
    """

    __tablename__ = "resource_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    scenario_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("planning_scenarios.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    team: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    quarter: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", server_default="draft"
    )
    computed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    parent_plan_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("resource_plans.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_baseline: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )
    label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    scenario: Mapped[Optional["PlanningScenario"]] = relationship("PlanningScenario")
    parent: Mapped[Optional["ResourcePlan"]] = relationship(
        "ResourcePlan",
        remote_side="ResourcePlan.id",
        foreign_keys=[parent_plan_id],
        back_populates="forks",
    )
    forks: Mapped[List["ResourcePlan"]] = relationship(
        "ResourcePlan",
        back_populates="parent",
        foreign_keys="[ResourcePlan.parent_plan_id]",
    )
    assignments: Mapped[List["ResourcePlanAssignment"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )
    dependencies: Mapped[List["PlanItemDependency"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )
    conflicts: Mapped[List["PlanConflict"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )
