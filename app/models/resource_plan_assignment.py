"""ResourcePlanAssignment — назначение фазы инициативы на сотрудника с датами."""

from datetime import date, datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.resource_plan import ResourcePlan
    from app.models.backlog_item import BacklogItem
    from app.models.employee import Employee


class ResourcePlanAssignment(Base, TimestampMixin):
    """Фаза инициативы в ресурсном плане.

    phase: analyst | dev | qa | opo
    part_number: 1..N для split-фаз (частичная сдача).
    """

    __tablename__ = "resource_plan_assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    plan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("resource_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    backlog_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("backlog_items.id", ondelete="CASCADE"), nullable=False
    )
    phase: Mapped[str] = mapped_column(String(16), nullable=False)
    employee_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    part_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    hours_allocated: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_on_critical_path: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    slack_days: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pinned_employee: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false(), index=True,
    )
    pinned_start: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false(),
    )
    pinned_split: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false(),
    )
    manual_edit_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    out_of_quarter: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    daily_hours_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Пользователь явно отредактировал список предшественников этой фазы
    # (через PATCH /assignments/{id} с predecessor_ids в payload).
    # _ensure_default_predecessors при пересчёте плана пропускает инициативу,
    # если хоть одна её фаза имеет этот флаг — иначе дефолтная цепочка
    # analyst→dev→qa→opo восстанавливала бы связь, которую пользователь
    # только что удалил.
    predecessors_user_set: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    plan: Mapped["ResourcePlan"] = relationship(back_populates="assignments")
    backlog_item: Mapped["BacklogItem"] = relationship("BacklogItem")
    employee: Mapped[Optional["Employee"]] = relationship("Employee")

    @property
    def is_pinned(self) -> bool:
        """Back-compat: True если хотя бы один pin-флаг включён."""
        return self.pinned_employee or self.pinned_start or self.pinned_split
