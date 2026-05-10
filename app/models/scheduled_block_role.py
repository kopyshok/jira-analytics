"""ScheduledBlockRole — M:N связь роли с заблокированным периодом."""

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import generate_uuid
from app.database import Base


class ScheduledBlockRole(Base):
    """Какие роли затронуты блоком (мульти-выбор)."""

    __tablename__ = "scheduled_block_role"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    block_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("scheduled_blocks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
    )
