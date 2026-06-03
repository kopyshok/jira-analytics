"""BacklogItem model - quarterly backlog items."""

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.issue import Issue
    from app.models.employee import Employee
    from app.models.scenario_allocation import ScenarioAllocation


class BacklogItem(Base, TimestampMixin):
    """Элемент квартального бэклога.

    Может быть привязан к Jira-задаче (``issue_id``) — тогда оценки
    синкаются из ``Issue.planned_*_hours``; либо создан вручную
    (``issue_id=NULL``) — PM вводит оценки сам и позже привязывает
    запись к созданной в Jira RFA/ITL.
    """

    __tablename__ = "backlog_items"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)

    project_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("projects.id"), nullable=True, index=True
    )
    issue_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("issues.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
        index=True,
    )

    # Legacy aggregate (computed by service on write from per-role estimates).
    estimate_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Per-role estimates (source: Issue.planned_*_hours when linked, else manual).
    estimate_analyst_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    estimate_dev_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    estimate_qa_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    estimate_opo_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Share of ОПЭ hours that go to analyst; rest goes to dev. 0.0..1.0; default 0.5.
    opo_analyst_ratio: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, default=0.5, server_default="0.5",
    )
    # PERT-множители для трёх точечной оценки: оптимистичный и пессимистичный сценарии.
    # t_o = estimate * optimistic_multiplier, t_p = estimate * pessimistic_multiplier.
    optimistic_multiplier: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.7, server_default="0.7",
    )
    pessimistic_multiplier: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.5, server_default="1.5",
    )

    priority: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    impact: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    risk: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    archived_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, index=False
    )

    # Режим планирования группы RFA: 'whole' (RFA целиком в сценарии) | 'by_epics'
    # (дочерние Эпики идут в сценарий, RFA-родитель — отдельной галочкой). Используется
    # только для RFA с дочерними Эпиками; на одиночных задачах остаётся 'whole'.
    planning_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="whole", server_default="whole",
    )
    # В режиме 'by_epics' — индивидуальный флаг участия в утверждаемом сценарии.
    # В режиме 'whole' не используется (поведение по дефолту: всегда включён).
    included_in_planning: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true(),
    )

    assignee_employee_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    customer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cost_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Jira involvement (0.0..1.0) and calendar duration (days) — sourced from Issue.
    # NULL = not set in Jira; solver falls back to hours_allocated / 8.
    involvement_analyst: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    involvement_dev: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    involvement_qa: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    involvement_launch: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    duration_analyst_days: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    duration_dev_days: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    duration_qa_days: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    duration_launch_days: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Per-item parallel staffing overrides (NULL = inherit from project, project NULL = 1).
    parallel_count_analyst: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    parallel_count_dev: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    parallel_count_qa: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Relationships
    project: Mapped[Optional["Project"]] = relationship(back_populates="backlog_items")
    issue: Mapped[Optional["Issue"]] = relationship("Issue")
    assignee: Mapped[Optional["Employee"]] = relationship(
        "Employee",
        foreign_keys=[assignee_employee_id],
    )
    allocations: Mapped[List["ScenarioAllocation"]] = relationship(
        back_populates="backlog_item"
    )

    def __repr__(self) -> str:
        return f"<BacklogItem {self.title[:30]}>"
