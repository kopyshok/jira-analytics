"""PlanItemDependency — зависимости между инициативами в плане ресурсного планирования."""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from app.models.resource_plan import ResourcePlan
    from app.models.backlog_item import BacklogItem


class PlanItemDependency(Base, TimestampMixin):
    """Зависимость FS/SS/FF/SF между двумя инициативами в рамках плана.

    dep_type: FS | SS | FF | SF
    source: manual | inferred
    """

    __tablename__ = "plan_item_dependencies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    plan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("resource_plans.id", ondelete="CASCADE"), index=True
    )
    from_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("backlog_items.id", ondelete="CASCADE")
    )
    to_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("backlog_items.id", ondelete="CASCADE")
    )
    dep_type: Mapped[str] = mapped_column(String(4), default="FS")
    lag_days: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(16), default="manual")

    plan: Mapped["ResourcePlan"] = relationship(back_populates="dependencies")
    from_item: Mapped["BacklogItem"] = relationship(foreign_keys=[from_item_id])
    to_item: Mapped["BacklogItem"] = relationship(foreign_keys=[to_item_id])
