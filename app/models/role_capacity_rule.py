"""RoleCapacityRule — шаблон правил квартала для новых сценариев.

Эти записи используются как source при копировании в ``scenario_rules``
в момент создания нового сценария (см. миграцию 027 и эндпоинт
``POST /planning/scenarios``). На уже созданные сценарии они не влияют —
активные сценарии редактируются через ``/planning/scenarios/{id}/rules``.
"""

from typing import Optional

from sqlalchemy import Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base


class RoleCapacityRule(Base, TimestampMixin):
    """Общие правила квартала — используются как шаблон при создании нового
    сценария. На активные сценарии не влияют: каждый сценарий хранит
    свои правила в ``scenario_rules`` (PUT ``/planning/scenarios/{id}/rules``).

    `role=NULL` — fallback «для всех ролей» (применяется если нет правила
    именно на роль сотрудника).
    """

    __tablename__ = "role_capacity_rules"
    __table_args__ = (
        UniqueConstraint(
            "year", "quarter", "role", "work_type_id",
            name="uq_role_capacity_rule_scope",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    quarter: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # None = для всех ролей
    work_type_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("mandatory_work_types.id"), nullable=False,
    )
    percent_of_norm: Mapped[float] = mapped_column(Float, nullable=False)

    def __repr__(self) -> str:
        return f"<RoleCapacityRule {self.year}Q{self.quarter} {self.role}/{self.work_type_id}: {self.percent_of_norm}%>"
