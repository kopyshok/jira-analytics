"""Реестр команд и групп внутри команды.

Имя команды по-прежнему хранится строкой в задачах, участии сотрудников,
сценариях и планах. Реестр адресуется по тому же имени и добавляет к нему
настройки — в первую очередь признак деления на группы.
"""

from typing import List

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class Team(Base, TimestampMixin):
    """Команда. Строка реестра, наполняется автоматически именами из данных."""

    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    has_subgroups: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )

    subgroups: Mapped[List["TeamSubgroup"]] = relationship(
        back_populates="team",
        cascade="all, delete-orphan",
        order_by="TeamSubgroup.sort_order",
    )

    def __repr__(self) -> str:
        return f"<Team {self.name}{' *groups' if self.has_subgroups else ''}>"


class TeamSubgroup(Base, TimestampMixin):
    """Группа внутри команды. Виртуальное деление, в Jira его нет."""

    __tablename__ = "team_subgroups"
    __table_args__ = (UniqueConstraint("team_id", "name", name="uq_team_subgroup_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    team: Mapped["Team"] = relationship(back_populates="subgroups")

    def __repr__(self) -> str:
        return f"<TeamSubgroup {self.name}>"
