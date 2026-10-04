"""Кто из команд уже взял мультикомандную RFA в работу (только чтение).

Мультикомандную RFA каждая команда планирует своим эпиком в своём сценарии.
По каждой команде-участнице считаем:

- ``taken`` — хотя бы один эпик команды под RFA включён в утверждённый
  сценарий своей команды текущего или будущего квартала (черновики, прошлые
  кварталы и сценарии другой команды не в счёт);
- ``done`` — иначе, если хотя бы один эпик команды выполнен (закрыт в Jira, не
  отменён); к нему — последний утверждённый квартал, где эпик был в плане;
- ``not_taken`` — эпик есть, но ни то, ни другое;
- ``no_epic`` — у команды нет эпика под этой RFA.

«Взят» и «выполнен» оба засчитываются в «в работе у K из N».

Участники — команды из поля Jira «участвующие команды» (в его порядке),
команда самой RFA и команды, которые завели под ней эпик, хотя в поле их нет.
Эпик — любой не отменённый прямой потомок RFA с командой, кроме листовых задач
по правилам иерархии (задачи и подзадачи OS/PMD и т.п.).

Четыре запроса на любой набор RFA: сами RFA, правила иерархии, их эпики,
включения эпиков в утверждённые сценарии.
"""

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Optional

from sqlalchemy.orm import Session

from app.models import BacklogItem, Issue, PlanningScenario, Project, ScenarioAllocation
from app.services.backlog_service import (
    CANCEL_STATUSES,
    parse_participating_teams,
    teams_make_multi_team,
)
from app.services.hierarchy_rules import is_planning_leaf, load_rules

TakeStatus = Literal["taken", "done", "not_taken", "no_epic"]
TAKEN: TakeStatus = "taken"
DONE: TakeStatus = "done"
NOT_TAKEN: TakeStatus = "not_taken"
NO_EPIC: TakeStatus = "no_epic"
# Засчитываются в «в работе у K из N».
COUNTED: frozenset[TakeStatus] = frozenset({TAKEN, DONE})

_CHUNK = 500


@dataclass(frozen=True)
class ScenarioMark:
    """Утверждённый сценарий, в который команда включила свой эпик."""

    id: str
    name: str
    year: int
    quarter: int

    @property
    def label(self) -> str:
        return f"{self.quarter} кв. {self.year}"


@dataclass
class TeamTake:
    """Статус одной команды-участницы.

    ``scenarios``: у «взят» — сценарии текущего и будущих кварталов; у
    «выполнен» — последний утверждённый, где был выполненный эпик (или пусто).
    """

    team: str
    status: TakeStatus
    scenarios: list[ScenarioMark] = field(default_factory=list)


@dataclass
class RfaProgress:
    """Статусы всех участников одной RFA."""

    teams: list[TeamTake]

    @property
    def taken(self) -> int:
        """K: команды, которые взяли работу или уже выполнили её."""
        return sum(1 for t in self.teams if t.status in COUNTED)

    @property
    def total(self) -> int:
        return len(self.teams)

    def status_of(self, team: Optional[str]) -> Optional[TakeStatus]:
        for t in self.teams:
            if t.team == team:
                return t.status
        return None


@dataclass(frozen=True)
class RowProgress:
    """Плашка строки: RFA, к которой строка относится, и статус её команды."""

    rfa: RfaProgress
    own_team: Optional[str]
    own_status: Optional[TakeStatus]


@dataclass(frozen=True)
class _Epic:
    rfa_id: str
    team: str
    done: bool


def _chunks(ids: list[str]) -> Iterator[list[str]]:
    for start in range(0, len(ids), _CHUNK):
        yield ids[start : start + _CHUNK]


def _quarter_number(raw: Optional[str]) -> Optional[int]:
    """«Q4» → 4. Пусто или мусор — None."""
    if not raw:
        return None
    digits = raw.strip().upper().removeprefix("Q")
    return int(digits) if digits.isdigit() and 1 <= int(digits) <= 4 else None


def _mark_key(m: ScenarioMark) -> tuple[int, int, str]:
    return (m.year, m.quarter, m.name)


def multi_team_progress(
    db: Session, rfa_issue_ids: Iterable[str], today: Optional[date] = None
) -> dict[str, RfaProgress]:
    """Статусы команд по каждой мультикомандной RFA из набора.

    ``rfa_issue_ids`` — id задач; не мультикомандные и несуществующие молча
    пропускаются, поэтому можно передать всех кандидатов разом (сами строки и
    их родителей). ``today`` — для проверок; по умолчанию сегодня.
    """
    ids = list({i for i in rfa_issue_ids if i})
    if not ids:
        return {}
    today = today or date.today()
    current = (today.year, (today.month - 1) // 3 + 1)

    rfas: dict[str, tuple[Optional[str], list[str]]] = {}
    for chunk in _chunks(ids):
        for rfa_id, team, raw in (
            db.query(Issue.id, Issue.team, Issue.participating_teams)
            .filter(Issue.id.in_(chunk))
            .all()
        ):
            if teams_make_multi_team(team, raw):
                rfas[rfa_id] = (team, parse_participating_teams(raw))
    if not rfas:
        return {}

    # Эпики: прямые потомки RFA с командой, кроме отменённых и листовых задач.
    rules = load_rules(db)
    epics: dict[str, _Epic] = {}
    for chunk in _chunks(list(rfas)):
        for epic_id, rfa_id, team, status, status_category, issue_type, project_key in (
            db.query(
                Issue.id,
                Issue.parent_id,
                Issue.team,
                Issue.status,
                Issue.status_category,
                Issue.issue_type,
                Project.key,
            )
            .outerjoin(Project, Issue.project_id == Project.id)
            .filter(Issue.parent_id.in_(chunk))
            .all()
        ):
            if not team or status in CANCEL_STATUSES:
                continue
            if is_planning_leaf(
                rules, project_key=project_key or "", issue_type=issue_type or "", has_parent=True
            ):
                continue
            epics[epic_id] = _Epic(rfa_id, team, status_category == "done")

    # Включения эпиков в утверждённые сценарии своей команды: текущий и будущие
    # кварталы — «взят»; у выполненных эпиков — и прошлые, для подписи.
    planned: dict[tuple[str, str], set[ScenarioMark]] = {}  # (rfa_id, team) → сценарии
    done_marks: dict[tuple[str, str], set[ScenarioMark]] = {}
    for chunk in _chunks(list(epics)):
        for epic_id, sid, name, year, quarter, scenario_team in (
            db.query(
                BacklogItem.issue_id,
                PlanningScenario.id,
                PlanningScenario.name,
                PlanningScenario.year,
                PlanningScenario.quarter,
                PlanningScenario.team,
            )
            .join(ScenarioAllocation, ScenarioAllocation.backlog_item_id == BacklogItem.id)
            .join(PlanningScenario, PlanningScenario.id == ScenarioAllocation.scenario_id)
            .filter(
                BacklogItem.issue_id.in_(chunk),
                PlanningScenario.status == "approved",
                ScenarioAllocation.included_flag.is_(True),
            )
            .all()
        ):
            epic = epics[epic_id]
            # Эпик переехал к другой команде — её прежний план не в счёт.
            # Сценарий без команды (на всех) считается.
            if scenario_team is not None and scenario_team != epic.team:
                continue
            q = _quarter_number(quarter)
            if year is None or q is None:
                continue
            mark = ScenarioMark(sid, name, year, q)
            key = (epic.rfa_id, epic.team)
            if (year, q) >= current:
                planned.setdefault(key, set()).add(mark)
            if epic.done:
                done_marks.setdefault(key, set()).add(mark)

    epic_teams: dict[str, set[str]] = {}
    done_teams: dict[str, set[str]] = {}
    for epic in epics.values():
        epic_teams.setdefault(epic.rfa_id, set()).add(epic.team)
        if epic.done:
            done_teams.setdefault(epic.rfa_id, set()).add(epic.team)

    result: dict[str, RfaProgress] = {}
    for rfa_id, (rfa_team, participating) in rfas.items():
        with_epic = epic_teams.get(rfa_id, set())
        with_done = done_teams.get(rfa_id, set())
        order = list(dict.fromkeys(participating))
        if rfa_team and rfa_team not in order:
            order.append(rfa_team)
        order += sorted(with_epic - set(order))
        teams: list[TeamTake] = []
        for team in order:
            key = (rfa_id, team)
            if key in planned:
                teams.append(TeamTake(team, TAKEN, sorted(planned[key], key=_mark_key)))
            elif team in with_done:
                last = max(done_marks.get(key, set()), key=_mark_key, default=None)
                teams.append(TeamTake(team, DONE, [last] if last else []))
            elif team in with_epic:
                teams.append(TeamTake(team, NOT_TAKEN))
            else:
                teams.append(TeamTake(team, NO_EPIC))
        result[rfa_id] = RfaProgress(teams=teams)
    return result


def row_progress(
    progress_by_rfa: Mapping[str, RfaProgress],
    *,
    issue_id: Optional[str],
    parent_id: Optional[str],
    team: Optional[str],
) -> Optional[RowProgress]:
    """Плашка строки: сама RFA или эпик мультикомандной RFA. Иначе — None.

    Строка, которая сама мультикомандная, показывает свою RFA, даже если её
    родитель тоже мультикомандный.
    """
    rfa = progress_by_rfa.get(issue_id) if issue_id else None
    if rfa is None and parent_id:
        rfa = progress_by_rfa.get(parent_id)
    if rfa is None:
        return None
    return RowProgress(rfa=rfa, own_team=team, own_status=rfa.status_of(team))
