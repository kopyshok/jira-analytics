"""TeamWorkTypeOverride — чем считается задача другой команды для команды исполнителя."""

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class TeamWorkTypeOverride(Base, TimestampMixin):
    """Вид нормированных работ, которым команда ``team`` считает работу своих
    людей над задачей ``backlog_item_id`` другой команды. Нет строки —
    «Технические задачи»."""

    __tablename__ = "team_work_type_overrides"
    __table_args__ = (
        UniqueConstraint("team", "backlog_item_id", name="uq_team_work_type_override"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    team: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    backlog_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("backlog_items.id", ondelete="CASCADE"), nullable=False
    )
    work_type_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("mandatory_work_types.id"), nullable=False
    )
