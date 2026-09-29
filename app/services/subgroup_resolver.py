"""Определение группы внутри команды для задачи.

Приоритет:
1. Проставлено явно на задаче (``assigned_subgroup_id``);
2. Ближайший предок с явно проставленной группой;
3. Предположение по исполнителю — его группа на дату закрытия задачи
   (открытой — на сегодня); поделённый между группами — без предположения.

Команды без включённого признака деления всегда дают пустой результат:
именно это гарантирует, что для них ничего не меняется.

Резолвер сознательно не встроен в ``CategoryResolver``: другая лесенка,
другой источник данных, общего кода нет.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Employee, EmployeeTeam, Issue, Team
from app.services import subgroup_shares as ss


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

    def __init__(self, db: Session, today: Optional[date] = None):
        self.db = db
        self._today = today or date.today()
        self._enabled_teams: Optional[set[str]] = None
        self._subgroup_team: dict[str, str] = {}  # subgroup_id -> имя команды
        # (account_id, команда) -> записи распределения исполнителя
        self._records: dict[tuple[str, str], ss.Records] = {}

    def _load(self) -> None:
        if self._enabled_teams is not None:
            return

        teams = self.db.query(Team).filter(Team.has_subgroups.is_(True)).all()
        self._enabled_teams = {t.name for t in teams}
        for t in teams:
            for g in t.subgroups:
                self._subgroup_team[g.id] = t.name

        account_of: dict[str, Optional[str]] = {
            e: a for e, a in self.db.query(Employee.id, Employee.jira_account_id)
        }
        # Запись распределения без единой строки участия в этой команде —
        # хвост участия, удалённого как ошибка ввода: по ней не угадываем.
        members = {
            (e, t)
            for e, t in self.db.query(EmployeeTeam.employee_id, EmployeeTeam.team).distinct()
        }
        for (emp_id, team_name), records in ss.load_all(self.db).items():
            account_id = account_of.get(emp_id)
            if account_id and (emp_id, team_name) in members:
                self._records[(account_id, team_name)] = records

    def _valid(self, subgroup_id: Optional[str], team: str) -> bool:
        """Группа годится, только если принадлежит команде задачи."""
        if not subgroup_id:
            return False
        return self._subgroup_team.get(subgroup_id) == team

    def _guess_day(
        self,
        status_category: Optional[str],
        resolved_at: Optional[datetime],
        status_changed_at: Optional[datetime],
    ) -> date:
        """День для угадывания группы: закрытая задача — дата закрытия, открытая — сегодня.

        «Закрытая» определяется по категории статуса, а не по наличию даты
        резолюции — у части задач ``resolved_at`` не проставлен. Дата закрытия —
        ``resolved_at``, а если её нет — дата последней смены статуса.

        ``resolved_at``/``status_changed_at`` хранятся в UTC, а дни распределения
        локальные; у границы перевода это даёт расхождение в несколько часов —
        считается приемлемым.
        """
        if status_category == "done":
            moment = resolved_at or status_changed_at
            if moment is not None:
                return moment.date()
        return self._today

    def _guess(self, account_id: Optional[str], team: str, day: date) -> Optional[str]:
        """Группа исполнителя в этот день. Поделённый между группами — без предположения."""
        records = self._records.get((account_id or "", team))
        if not records:
            return None
        group = ss.single_group_on(records, day)
        return group if self._valid(group, team) else None

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

        # 3. Предположение по исполнителю — его группа на дату
        day = self._guess_day(issue.status_category, issue.resolved_at, issue.status_changed_at)
        guess = self._guess(issue.assignee_account_id, team, day)
        if guess:
            return SubgroupResolution(subgroup_id=guess, source=SubgroupSource.GUESS)

        return empty

    # --- Материализация -----------------------------------------------------

    def _walk(
        self,
        issue_id: str,
        team: str,
        account_id: Optional[str],
        status_category: Optional[str],
        resolved_at: Optional[datetime],
        status_changed_at: Optional[datetime],
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

        day = self._guess_day(status_category, resolved_at, status_changed_at)
        return self._guess(account_id, team, day)

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
            Issue.id,
            Issue.team,
            Issue.assignee_account_id,
            Issue.status_category,
            Issue.resolved_at,
            Issue.status_changed_at,
            Issue.effective_subgroup_id,
        )
        if team is not None:
            q = q.filter(Issue.team == team)

        updates: dict[Optional[str], list[str]] = {}
        changed = 0
        for iid, team_name, account_id, status_category, resolved_at, status_changed_at, current in q.all():
            value = (
                self._walk(
                    iid,
                    team_name,
                    account_id,
                    status_category,
                    resolved_at,
                    status_changed_at,
                    parents,
                    assigned,
                )
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
