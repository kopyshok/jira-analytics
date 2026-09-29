"""Личная настройка сотрудника: вовлечённость и свои нормированные работы."""

from typing import List, Optional

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class EmployeePersonalSetting(Base, TimestampMixin):
    """Действует с квартала до следующей записи этого сотрудника.

    ``involvement`` — личная вовлечённость (0–1), None — как обычно.
    ``normed_custom`` — свои проценты нормированных работ (строки ``normed``;
    пусто — нормированных работ нет); False — по правилам роли.
    """

    __tablename__ = "employee_personal_settings"
    __table_args__ = (
        UniqueConstraint(
            "employee_id", "effective_year", "effective_quarter",
            name="uq_employee_personal_setting_scope",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    effective_year: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_quarter: Mapped[int] = mapped_column(Integer, nullable=False)
    involvement: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    normed_custom: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    normed: Mapped[List["EmployeePersonalNormed"]] = relationship(
        "EmployeePersonalNormed", cascade="all, delete-orphan"
    )


class EmployeePersonalNormed(Base):
    """Свой процент нормы сотрудника по виду работ, уменьшающему запас на проекты."""

    __tablename__ = "employee_personal_normed"
    __table_args__ = (
        UniqueConstraint("setting_id", "work_type_id", name="uq_employee_personal_normed"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    setting_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("employee_personal_settings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    work_type_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("mandatory_work_types.id"), nullable=False
    )
    percent_of_norm: Mapped[float] = mapped_column(Float, nullable=False)
