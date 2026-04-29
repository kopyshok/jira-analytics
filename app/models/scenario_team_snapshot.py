"""ScenarioTeamSnapshot — состав команды на момент утверждения сценария.

Копия employees команды (display_name, role, hours_per_day, is_active) —
позволяет показать ревизию даже если сотрудник позже удалён или сменил роль.
"""
from typing import Optional, TYPE_CHECKING
from sqlalchemy import Boolean, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.scenario_revision import ScenarioRevision


class ScenarioTeamSnapshot(Base, TimestampMixin):
    __tablename__ = "scenario_team_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenario_revisions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    employee_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    hours_per_day: Mapped[float] = mapped_column(Float, nullable=False, default=8.0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_external: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    revision: Mapped["ScenarioRevision"] = relationship(back_populates="team_snapshots")
