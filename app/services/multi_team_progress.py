"""Кто из команд уже взял мультикомандную RFA в работу (только чтение).

Мультикомандную RFA каждая команда планирует своим эпиком в своём сценарии.
По каждой команде-участнице считаем:

- ``taken`` — хотя бы один эпик команды под RFA включён в утверждённый
  сценарий текущего или будущего квартала (черновики и прошлые кварталы не в
  счёт; статус задачи в Jira не смотрим);
- ``not_taken`` — эпик есть, но такого включения нет;
- ``no_epic`` — у команды нет эпика под этой RFA.

Участники — команды из поля Jira «участвующие команды» (в его порядке),
команда самой RFA и команды, которые завели под ней эпик, хотя в поле их нет.
Эпик — прямой потомок RFA; отменённый эпик не считается.

Три запроса на любой набор RFA: сами RFA, их эпики, включения эпиков в
утверждённые сценарии.
"""

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.models import BacklogItem, Issue, PlanningScenario, ScenarioAllocation
from app.services.backlog_service import (
    CANCEL_STATUSES,
    parse_participating_teams,
    teams_make_multi_team,
)

TAKEN = "taken"
NOT_TAKEN = "not_taken"
NO_EPIC = "no_epic"

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
    """Статус одной команды-участницы."""

    team: str
    status: str
    scenarios: list[ScenarioMark] = field(default_factory=list)


@dataclass
class RfaProgress:
    """Статусы всех участников одной RFA."""

    teams: list[TeamTake]

    @property
    def taken(self) -> int:
        return sum(1 for t in self.teams if t.status == TAKEN)

    @property
    def total(self) -> int:
        return len(self.teams)

    def status_of(self, team: Optional[str]) -> Optional[str]:
        for t in self.teams:
            if t.team == team:
                return t.status
        return None


@dataclass(frozen=True)
class RowProgress:
    """Плашка строки: RFA, к которой строка относится, и статус её команды."""

    rfa: RfaProgress
    own_team: Optional[str]
    own_status: Optional[str]


def _chunks(ids: list[str]) -> Iterator[list[str]]:
    for start in range(0, len(ids), _CHUNK):
        yield ids[start : start + _CHUNK]


def _quarter_number(raw: Optional[str]) -> Optional[int]:
    """«Q4» → 4. Пусто или мусор — None."""
    if not raw:
        return None
    digits = raw.strip().upper().removeprefix("Q")
    return int(digits) if digits.isdigit() and 1 <= int(digits) <= 4 else None


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

    # Эпики: прямые потомки RFA с командой, кроме отменённых.
    epics: dict[str, tuple[str, str]] = {}  # epic_id → (rfa_id, team)
    for chunk in _chunks(list(rfas)):
        for epic_id, rfa_id, team, status in (
            db.query(Issue.id, Issue.parent_id, Issue.team, Issue.status)
            .filter(Issue.parent_id.in_(chunk))
            .all()
        ):
            if team and status not in CANCEL_STATUSES:
                epics[epic_id] = (rfa_id, team)

    # Включения эпиков в утверждённые сценарии текущего и будущих кварталов.
    marks: dict[tuple[str, str], set[ScenarioMark]] = {}  # (rfa_id, team) → сценарии
    for chunk in _chunks(list(epics)):
        for epic_id, sid, name, year, quarter in (
            db.query(
                BacklogItem.issue_id,
                PlanningScenario.id,
                PlanningScenario.name,
                PlanningScenario.year,
                PlanningScenario.quarter,
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
            q = _quarter_number(quarter)
            if year is None or q is None or (year, q) < current:
                continue
            marks.setdefault(epics[epic_id], set()).add(ScenarioMark(sid, name, year, q))

    epic_teams: dict[str, set[str]] = {}
    for rfa_id, team in epics.values():
        epic_teams.setdefault(rfa_id, set()).add(team)

    result: dict[str, RfaProgress] = {}
    for rfa_id, (rfa_team, participating) in rfas.items():
        with_epic = epic_teams.get(rfa_id, set())
        order = list(dict.fromkeys(participating))
        if rfa_team and rfa_team not in order:
            order.append(rfa_team)
        order += sorted(with_epic - set(order))
        teams: list[TeamTake] = []
        for team in order:
            scenarios = sorted(
                marks.get((rfa_id, team), set()), key=lambda m: (m.year, m.quarter, m.name)
            )
            status = TAKEN if scenarios else NOT_TAKEN if team in with_epic else NO_EPIC
            teams.append(TeamTake(team=team, status=status, scenarios=scenarios))
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
