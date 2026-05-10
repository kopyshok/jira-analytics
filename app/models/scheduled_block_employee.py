"""ScheduledBlockEmployee — M:N связь сотрудника с заблокированным периодом."""

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import generate_uuid
from app.database import Base


class ScheduledBlockEmployee(Base):
    """Какие конкретные сотрудники дополнительно затронуты блоком."""

    __tablename__ = "scheduled_block_employee"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    block_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("scheduled_blocks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    employee_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )
