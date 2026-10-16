"""Запуск консоли Jira/Confluence: что спросили и что ответила система.

Хранятся последние 30 запусков (чистит эндпоинт при записи нового). Токена тут
нет; при включённом скрытии результат уже без имён и почты.
"""
from typing import Optional

from sqlalchemy import Boolean, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class ConsoleRun(Base, TimestampMixin):
    """Один запуск консоли. Имя автора — снимком: учётку могут удалить."""

    __tablename__ = "console_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    user_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    target: Mapped[str] = mapped_column(String(16), nullable=False)
    masked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    output_text: Mapped[str] = mapped_column(Text, nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (Index("ix_console_runs_created_at", "created_at"),)
