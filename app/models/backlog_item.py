"""BacklogItem model - quarterly backlog items."""

from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.issue import Issue
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

    priority: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    impact: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    risk: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Relationships
    project: Mapped[Optional["Project"]] = relationship(back_populates="backlog_items")
    issue: Mapped[Optional["Issue"]] = relationship("Issue")
    allocations: Mapped[List["ScenarioAllocation"]] = relationship(
        back_populates="backlog_item"
    )

    def __repr__(self) -> str:
        return f"<BacklogItem {self.title[:30]}>"
