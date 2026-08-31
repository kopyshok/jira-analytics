"""Определение группы внутри команды для задачи.

Приоритет:
1. Проставлено явно на задаче (``assigned_subgroup_id``);
2. Ближайший предок с явно проставленной группой;
3. Предположение по исполнителю — группа, к которой он приписан в этой команде.

Команды без включённого признака деления всегда дают пустой результат:
именно это гарантирует, что для них ничего не меняется.

Резолвер сознательно не встроен в ``CategoryResolver``: другая лесенка,
другой источник данных, общего кода нет.
"""

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Employee, EmployeeTeam, Issue, Team


class SubgroupSource:
    ASSIGNED = "assigned"      # проставлено человеком
    INHERITED = "inherited"    # от родителя
    GUESS = "guess"            # предположение по исполнителю
    NONE = "none"


@dataclass
class SubgroupResolution:
    """Результат резолвинга группы для задачи."""

    subgroup_id: Optional[str]
    source: str
    source_entity_key: Optional[str] = None


class SubgroupResolver:
    """Резолвер группы. Кэши живут на время экземпляра."""

    def __init__(self, db: Session):
        self.db = db
        self._enabled_teams: Optional[set[str]] = None
        self._subgroup_team: dict[str, str] = {}           # subgroup_id -> имя команды
        self._by_account: dict[tuple[str, str], str] = {}  # (account_id, команда) -> subgroup_id

    def _load(self) -> None:
        if self._enabled_teams is not None:
            return

        teams = self.db.query(Team).filter(Team.has_subgroups.is_(True)).all()
        self._enabled_teams = {t.name for t in teams}
        for t in teams:
            for g in t.subgroups:
                self._subgroup_team[g.id] = t.name

        rows = (
            self.db.query(
                EmployeeTeam.team, EmployeeTeam.subgroup_id, Employee.jira_account_id
            )
            .join(Employee, Employee.id == EmployeeTeam.employee_id)
            .filter(EmployeeTeam.subgroup_id.isnot(None))
            .all()
        )
        for team_name, subgroup_id, account_id in rows:
            if account_id:
                self._by_account[(account_id, team_name)] = subgroup_id

    def _valid(self, subgroup_id: Optional[str], team: str) -> bool:
        """Группа годится, только если принадлежит команде задачи."""
        if not subgroup_id:
            return False
        return self._subgroup_team.get(subgroup_id) == team

    def resolve_for_issue(self, issue: Issue) -> SubgroupResolution:
        """Определить группу задачи по лесенке."""
        self._load()
        empty = SubgroupResolution(subgroup_id=None, source=SubgroupSource.NONE)

        team = issue.team
        if not team or team not in (self._enabled_teams or set()):
            return empty

        # 1. Явно на задаче
        if self._valid(issue.assigned_subgroup_id, team):
            return SubgroupResolution(
                subgroup_id=issue.assigned_subgroup_id,
                source=SubgroupSource.ASSIGNED,
                source_entity_key=issue.key,
            )

        # 2. Ближайший предок с явной группой
        current: Optional[Issue] = issue.parent
        visited: set[str] = {issue.id}
        while current is not None and current.id not in visited:
            visited.add(current.id)
            if self._valid(current.assigned_subgroup_id, team):
                return SubgroupResolution(
                    subgroup_id=current.assigned_subgroup_id,
                    source=SubgroupSource.INHERITED,
                    source_entity_key=current.key,
                )
            current = current.parent

        # 3. Предположение по исполнителю
        guess = self._by_account.get((issue.assignee_account_id or "", team))
        if self._valid(guess, team):
            return SubgroupResolution(subgroup_id=guess, source=SubgroupSource.GUESS)

        return empty
