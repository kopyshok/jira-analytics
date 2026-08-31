"""Реестр команд: наполнение именами и настройки групп внутри команды."""

from typing import Optional

from sqlalchemy.orm import Session

from app.models import EmployeeTeam, Issue, Team, TeamSubgroup


class TeamRegistryService:
    """Работа с реестром команд и группами внутри них."""

    def __init__(self, db: Session):
        self.db = db

    def sync_names(self) -> int:
        """Завести в реестре команды, встречающиеся в данных. Вернуть число новых."""
        known = {name for (name,) in self.db.query(Team.name).all()}

        found: set[str] = set()
        for (value,) in self.db.query(Issue.team).filter(Issue.team.isnot(None)).distinct():
            if value:
                found.add(value)
        for (value,) in self.db.query(EmployeeTeam.team).distinct():
            if value:
                found.add(value)

        new_names = sorted(found - known)
        for name in new_names:
            self.db.add(Team(name=name))
        if new_names:
            self.db.commit()
        return len(new_names)

    def get(self, name: str) -> Optional[Team]:
        return self.db.query(Team).filter(Team.name == name).first()

    def set_has_subgroups(self, name: str, enabled: bool) -> Team:
        """Включить или выключить деление команды на группы.

        Выключение группы не удаляет: признак снят — разрезы скрыты, данные
        целы, включение возвращает всё как было. Это и есть путь отката.
        """
        team = self.get(name)
        if team is None:
            team = Team(name=name)
            self.db.add(team)
        team.has_subgroups = enabled
        self.db.commit()
        return team

    def add_subgroup(self, name: str, subgroup_name: str) -> TeamSubgroup:
        team = self.get(name)
        if team is None:
            raise ValueError(f"Команда не найдена: {name}")
        group = TeamSubgroup(
            team_id=team.id, name=subgroup_name, sort_order=len(team.subgroups) + 1
        )
        self.db.add(group)
        self.db.commit()
        return group

    def rename_subgroup(self, subgroup_id: str, subgroup_name: str) -> TeamSubgroup:
        group = self.db.query(TeamSubgroup).filter(TeamSubgroup.id == subgroup_id).one()
        group.name = subgroup_name
        self.db.commit()
        return group

    def delete_subgroup(self, subgroup_id: str) -> None:
        """Удалить группу. Приписки сотрудников и задач обнуляются каскадом."""
        group = self.db.query(TeamSubgroup).filter(TeamSubgroup.id == subgroup_id).one()
        self.db.delete(group)
        self.db.commit()

    def assign_employee(
        self, employee_id: str, team: str, subgroup_id: Optional[str]
    ) -> None:
        """Приписать сотрудника к группе во всех его строках участия в команде."""
        rows = (
            self.db.query(EmployeeTeam)
            .filter(EmployeeTeam.employee_id == employee_id, EmployeeTeam.team == team)
            .all()
        )
        for row in rows:
            row.subgroup_id = subgroup_id
        self.db.commit()
