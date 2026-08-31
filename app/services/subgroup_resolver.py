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

    # --- Материализация -----------------------------------------------------

    def _walk(
        self,
        issue_id: str,
        team: str,
        account_id: Optional[str],
        parents: dict[str, Optional[str]],
        assigned: dict[str, Optional[str]],
    ) -> Optional[str]:
        """Та же лесенка, но по загруженным в память картам родителей."""
        if self._valid(assigned.get(issue_id), team):
            return assigned[issue_id]

        visited = {issue_id}
        current = parents.get(issue_id)
        while current is not None and current not in visited:
            visited.add(current)
            if self._valid(assigned.get(current), team):
                return assigned[current]
            current = parents.get(current)

        guess = self._by_account.get((account_id or "", team))
        return guess if self._valid(guess, team) else None

    def recompute_effective(self, team: Optional[str] = None) -> int:
        """Пересчитать ``Issue.effective_subgroup_id``. Вернуть число правок.

        ``team`` сужает пересчёт до одной команды. Задачи команд без признака
        деления обнуляются — так снятие признака убирает за собой хвост.
        """
        self._load()
        enabled = self._enabled_teams or set()

        parents: dict[str, Optional[str]] = {}
        assigned: dict[str, Optional[str]] = {}
        for iid, pid, aid in self.db.query(
            Issue.id, Issue.parent_id, Issue.assigned_subgroup_id
        ).all():
            parents[iid] = pid
            assigned[iid] = aid

        q = self.db.query(
            Issue.id, Issue.team, Issue.assignee_account_id, Issue.effective_subgroup_id
        )
        if team is not None:
            q = q.filter(Issue.team == team)

        updates: dict[Optional[str], list[str]] = {}
        changed = 0
        for iid, team_name, account_id, current in q.all():
            value = (
                self._walk(iid, team_name, account_id, parents, assigned)
                if team_name in enabled
                else None
            )
            if value != current:
                updates.setdefault(value, []).append(iid)
                changed += 1

        for value, ids in updates.items():
            for i in range(0, len(ids), 400):
                self.db.query(Issue).filter(Issue.id.in_(ids[i : i + 400])).update(
                    {Issue.effective_subgroup_id: value}, synchronize_session=False
                )
        if changed:
            self.db.commit()
        return changed
