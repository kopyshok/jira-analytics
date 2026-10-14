"""Переезд на Jira Data Center: отчёт пробного прогона и решения администратора.

Отчёт пересоздаётся каждым пробным прогоном. Решения живут отдельно и
переживают повторные прогоны: ключ решения — то, что при переезде не
меняется (облачный номер поля, ключ задачи, внутренний номер сотрудника).
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class JiraMigrationReport(Base, TimestampMixin):
    """Отчёт пробного прогона, итог применения и сверка после."""

    __tablename__ = "jira_migration_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    # running | done | failed
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Сводка для страницы (JSON-строка).
    report_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Соответствия для применения: ключ задачи → id в новой Jira и т. п. (JSON-строка).
    maps_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    apply_summary_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Полная синхронизация, запущенная после применения.
    sync_run_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    post_check_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class JiraMigrationDecision(Base, TimestampMixin):
    """Решение администратора по пункту отчёта (JSON-строка в ``decision_json``)."""

    __tablename__ = "jira_migration_decisions"
    __table_args__ = (
        UniqueConstraint("kind", "item_key", name="uq_jira_migration_decision"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    # field | issue | person
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    item_key: Mapped[str] = mapped_column(String(128), nullable=False)
    decision_json: Mapped[str] = mapped_column(Text, nullable=False)
    decided_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
