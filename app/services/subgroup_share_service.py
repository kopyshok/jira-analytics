"""Запись распределения сотрудника по группам внутри команды.

Перевод — запись «100 % в новую группу» с даты, деление — запись с
несколькими группами. Запись с той же датой заменяется целиком.
"""

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.models import EmployeeSubgroupShare, EmployeeTeam
from app.services import subgroup_shares as ss
from app.services.subgroup_resolver import SubgroupResolver


class SubgroupShareService:
    """Правка истории распределения. Каждая правка пересчитывает группы задач."""

    def __init__(self, db: Session):
        self.db = db

    def history(self, employee_id: str, team: str) -> ss.Records:
        """История записей распределения сотрудника в команде, по возрастанию даты."""
        return ss.load_team(self.db, team, [employee_id]).get(employee_id, [])

    def set_record(
        self,
        employee_id: str,
        team: str,
        valid_from: Optional[date],
        shares: dict[str, int],
    ) -> ss.Records:
        """Задать запись с даты (``None`` — с начала участия). Вернуть историю."""
        groups = dict(ss.team_subgroups(self.db, team))
        if not groups:
            raise ValueError("У команды нет деления на группы")
        if not shares:
            raise ValueError("Укажите хотя бы одну группу")
        for subgroup_id, percent in shares.items():
            if subgroup_id not in groups:
                raise ValueError("Группа не из этой команды")
            if not isinstance(percent, int) or not 1 <= percent <= 100:
                raise ValueError("Доля — целое число от 1 до 100")
        if sum(shares.values()) != 100:
            raise ValueError("Сумма долей должна быть 100%")
        if not self._lock_members(employee_id, team):
            raise ValueError("Сотрудник не состоит в команде")

        self._delete_rows(employee_id, team, valid_from)
        for subgroup_id, percent in shares.items():
            self.db.add(
                EmployeeSubgroupShare(
                    employee_id=employee_id,
                    team=team,
                    valid_from=valid_from,
                    subgroup_id=subgroup_id,
                    percent=percent,
                )
            )
        return self._finish(employee_id, team)

    def delete_record(
        self, employee_id: str, team: str, valid_from: Optional[date]
    ) -> ss.Records:
        """Удалить запись с этой датой. Вернуть историю."""
        self._lock_members(employee_id, team)
        if not self._delete_rows(employee_id, team, valid_from):
            raise LookupError("Запись не найдена")
        return self._finish(employee_id, team)

    def _lock_members(self, employee_id: str, team: str) -> list[str]:
        """Заблокировать строки участия сотрудника в команде на время правки.

        Без блокировки два одновременных сохранения на одну и ту же дату
        проходят проверки независимо и вместе дают 200% вместо 100%. SQLite
        FOR UPDATE игнорирует, на PostgreSQL блокировка сериализует
        одновременные правки одного сотрудника.
        """
        return [
            row_id
            for (row_id,) in self.db.query(EmployeeTeam.id)
            .filter(EmployeeTeam.employee_id == employee_id, EmployeeTeam.team == team)
            .order_by(EmployeeTeam.id)
            .with_for_update()
            .all()
        ]

    def _delete_rows(
        self, employee_id: str, team: str, valid_from: Optional[date]
    ) -> int:
        q = self.db.query(EmployeeSubgroupShare).filter(
            EmployeeSubgroupShare.employee_id == employee_id,
            EmployeeSubgroupShare.team == team,
        )
        q = (
            q.filter(EmployeeSubgroupShare.valid_from.is_(None))
            if valid_from is None
            else q.filter(EmployeeSubgroupShare.valid_from == valid_from)
        )
        return q.delete(synchronize_session=False)

    def _finish(self, employee_id: str, team: str) -> ss.Records:
        self.db.flush()
        records = self.history(employee_id, team)
        self.db.commit()
        # Группа человека — третья ступень лесенки группы задачи.
        SubgroupResolver(self.db).recompute_effective(team=team)
        return records
