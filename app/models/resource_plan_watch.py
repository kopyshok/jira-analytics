"""ResourcePlanWatch — сотрудник в списке наблюдения ресурсного плана."""

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class ResourcePlanWatch(Base, TimestampMixin):
    """Человек из любой команды, чью загрузку план показывает в «Загрузке по
    дням» секцией «Наблюдаемые» — при подборе людей. Список общий для плана:
    его видят все, кто открывает план."""

    __tablename__ = "resource_plan_watch"
    __table_args__ = (
        UniqueConstraint("plan_id", "employee_id", name="uq_resource_plan_watch"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    # Отдельный индекс по плану не нужен: его покрывает уникальный (план, сотрудник).
    plan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("resource_plans.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
