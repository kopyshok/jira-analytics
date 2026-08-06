"""Справочники раздела KPI. Метрики хранятся как данные, а не как код."""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class KpiMetric(Base, TimestampMixin):
    """Определение метрики. calc_kind: ratio | norm_to_fact | score_to_max."""

    __tablename__ = "kpi_metrics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    calc_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # ratio: оба набора; norm_to_fact и score_to_max: только numerator_json
    numerator_json: Mapped[str] = mapped_column(Text, nullable=False)
    denominator_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # norm_to_fact: имя поля задачи с фактом; score_to_max: список полей и максимум
    fact_field: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    score_fields: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    score_max: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    invert: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cap_at_100: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class KpiProfile(Base, TimestampMixin):
    """Набор метрик с весами, привязанный к ролям сотрудников."""

    __tablename__ = "kpi_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    target_pct: Mapped[float] = mapped_column(Float, nullable=False, default=80.0)
    warn_band_pct: Mapped[float] = mapped_column(Float, nullable=False, default=10.0)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    metrics: Mapped[list["KpiProfileMetric"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", lazy="selectin"
    )
    roles: Mapped[list["KpiProfileRole"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", lazy="selectin"
    )


class KpiProfileRole(Base, TimestampMixin):
    """Роль сотрудника, которую оценивает профиль.

    Роль уникальна глобально: сотрудник не может одновременно оцениваться
    двумя профилями, иначе выбор был бы недетерминированным. Профиля «по
    умолчанию» больше нет — сотрудник, чья роль не привязана ни к одному
    профилю, в ведомость не попадает (см. спеку доработок, раздел 2).
    """

    __tablename__ = "kpi_profile_roles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("kpi_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    profile: Mapped["KpiProfile"] = relationship(back_populates="roles")


class KpiProfileMetric(Base, TimestampMixin):
    """Вес метрики внутри профиля. Сумма весов профиля обязана равняться 1."""

    __tablename__ = "kpi_profile_metrics"
    __table_args__ = (UniqueConstraint("profile_id", "metric_id", name="uq_profile_metric"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("kpi_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    metric_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("kpi_metrics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    profile: Mapped["KpiProfile"] = relationship(back_populates="metrics")
    metric: Mapped["KpiMetric"] = relationship(lazy="selectin")


class KpiCycleTimeNorm(Base, TimestampMixin):
    """Плановый Cycle Time на команду и квартал."""

    __tablename__ = "kpi_cycle_time_norms"
    __table_args__ = (UniqueConstraint("team", "year", "quarter", name="uq_kpi_ct_norm"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    team: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    quarter: Mapped[int] = mapped_column(Integer, nullable=False)
    norm_value: Mapped[float] = mapped_column(Float, nullable=False)


class KpiApproval(Base, TimestampMixin):
    """Снимок утверждённого месяца: результат вместе с весами и правилами на тот момент."""

    __tablename__ = "kpi_approvals"
    __table_args__ = (UniqueConstraint("team", "year", "month", name="uq_kpi_approval"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    team: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    approved_by: Mapped[str] = mapped_column(String(255), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
