"""ScenarioRevision model — one record per scenario approval event."""

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.planning_scenario import PlanningScenario
    from app.models.scenario_revision_item import ScenarioRevisionItem
    from app.models.scenario_capacity_snapshot import ScenarioCapacitySnapshot
    from app.models.scenario_norm_snapshot import ScenarioNormSnapshot
    from app.models.scenario_absence_snapshot import ScenarioAbsenceSnapshot
    from app.models.scenario_team_snapshot import ScenarioTeamSnapshot
    from app.models.scenario_calendar_snapshot import ScenarioCalendarSnapshot
    from app.models.scenario_rules_snapshot import ScenarioRulesSnapshot
    from app.models.scenario_allocation_snapshot import ScenarioAllocationSnapshot
    from app.models.scenario_allocation_breakdown_snapshot import ScenarioAllocationBreakdownSnapshot
    from app.models.scenario_dictionary_snapshot import ScenarioDictionarySnapshot
    from app.models.user import User


class ScenarioRevision(Base, TimestampMixin):
    __tablename__ = "scenario_revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("planning_scenarios.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    parent_revision_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("scenario_revisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    algo_version: Mapped[str] = mapped_column(String(16), nullable=False, default="v1")

    scenario: Mapped["PlanningScenario"] = relationship(back_populates="revisions")
    items: Mapped[List["ScenarioRevisionItem"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )
    capacity_snapshots: Mapped[List["ScenarioCapacitySnapshot"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )
    norm_snapshots: Mapped[List["ScenarioNormSnapshot"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )
    absence_snapshots: Mapped[List["ScenarioAbsenceSnapshot"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )
    team_snapshots: Mapped[List["ScenarioTeamSnapshot"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )
    calendar_snapshots: Mapped[List["ScenarioCalendarSnapshot"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )
    rules_snapshots: Mapped[List["ScenarioRulesSnapshot"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )
    allocation_snapshots: Mapped[List["ScenarioAllocationSnapshot"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )
    allocation_breakdown_snapshots: Mapped[List["ScenarioAllocationBreakdownSnapshot"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )
    dictionary_snapshots: Mapped[List["ScenarioDictionarySnapshot"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )
    approved_by: Mapped[Optional["User"]] = relationship(foreign_keys=[approved_by_user_id])

    def __repr__(self) -> str:
        return f"<ScenarioRevision scenario={self.scenario_id} rev={self.revision_number}>"
