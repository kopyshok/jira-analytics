"""Кто из команд уже взял мультикомандную RFA в работу.

«Взят» — эпик команды под RFA включён в утверждённый сценарий своей команды
текущего или будущего квартала. Черновики, снятые галочки, прошлые кварталы и
сценарии чужой команды не считаются. «Выполнен» — эпик команды закрыт в Jira;
тоже засчитывается. Листовые задачи (по правилам иерархии) — не эпики.
"""
import json
from datetime import date
from typing import Optional

from sqlalchemy import event

from app.models import (
    BacklogItem, HierarchyRule, Issue, PlanningScenario, Project, ScenarioAllocation,
)
from app.services.multi_team_progress import (
    DONE,
    NO_EPIC,
    NOT_TAKEN,
    TAKEN,
    multi_team_progress,
    row_progress,
)

TEAM_A = "Команда А"
TEAM_B = "Команда Б"
TEAM_C = "Команда В"
TODAY = date(2026, 10, 4)  # IV кв. 2026


def _project(db) -> None:
    db.add(Project(id="p-1", key="RFA", jira_project_id="jp-1", name="RFA"))
    db.add(Project(id="p-os", key="OS", jira_project_id="jp-os", name="OS"))
    db.flush()


def _issue(
    db, key: str, *, team: Optional[str], parent: Optional[str] = None,
    participating: Optional[list[str]] = None, status: str = "Backlog",
    issue_type: str = "Эпик", status_category: Optional[str] = None, project: str = "p-1",
) -> str:
    db.add(Issue(
        id=f"i-{key}", key=key, jira_issue_id=f"j-{key}", summary=key, issue_type=issue_type,
        status=status, status_category=status_category, project_id=project,
        parent_id=f"i-{parent}" if parent else None,
        team=team, category="initiatives_rfa",
        participating_teams=json.dumps(participating, ensure_ascii=False) if participating else None,
    ))
    db.flush()
    return f"i-{key}"


def _backlog(db, key: str) -> str:
    db.add(BacklogItem(id=f"bi-{key}", issue_id=f"i-{key}", title=key))
    db.flush()
    return f"bi-{key}"


def _scenario(
    db, sid: str, *, team: str, year: int, quarter: int, status: str = "approved",
    name: Optional[str] = None,
) -> str:
    db.add(PlanningScenario(
        id=sid, name=name or sid, year=year, quarter=f"Q{quarter}", status=status, team=team,
    ))
    db.flush()
    return sid


def _include(db, sid: str, key: str, included: bool = True) -> None:
    db.add(ScenarioAllocation(
        scenario_id=sid, backlog_item_id=f"bi-{key}", included_flag=included, planned_hours=0,
    ))
    db.flush()


def _epic(db, key: str, team: str, parent: str = "RFA-1", **kwargs) -> None:
    """Эпик под RFA с элементом бэклога."""
    _issue(db, key, team=team, parent=parent, **kwargs)
    _backlog(db, key)


def _rfa(db, key: str = "RFA-1", *, team: str = TEAM_A, participating=None) -> str:
    return _issue(
        db, key, team=team, issue_type="Инициатива",
        participating=participating if participating is not None else [TEAM_A, TEAM_B, TEAM_C],
    )


def _statuses(progress) -> dict[str, str]:
    return {t.team: t.status for t in progress.teams}


def test_three_teams_one_taken(db_session):
    """Три команды: А взяла (эпик в утверждённом сценарии IV кв.), у Б эпик есть,
    но не включён, у В эпика нет."""
    db = db_session
    _project(db)
    rfa = _rfa(db)
    _issue(db, "OS-A", team=TEAM_A, parent="RFA-1")
    _backlog(db, "OS-A")
    _issue(db, "OS-B", team=TEAM_B, parent="RFA-1")
    _backlog(db, "OS-B")
    _scenario(db, "s-a", team=TEAM_A, year=2026, quarter=4, name="План А IV кв.")
    _include(db, "s-a", "OS-A")

    progress = multi_team_progress(db, [rfa], today=TODAY)[rfa]

    assert [t.team for t in progress.teams] == [TEAM_A, TEAM_B, TEAM_C]
    assert _statuses(progress) == {TEAM_A: TAKEN, TEAM_B: NOT_TAKEN, TEAM_C: NO_EPIC}
    assert (progress.taken, progress.total) == (1, 3)
    taken = progress.teams[0]
    assert [(s.name, s.label) for s in taken.scenarios] == [("План А IV кв.", "4 кв. 2026")]
    assert progress.teams[1].scenarios == []


def test_past_quarter_ignored_current_and_future_count(db_session):
    """Утверждённый сценарий прошлого квартала не считается; будущего — считается."""
    db = db_session
    _project(db)
    rfa = _rfa(db)
    _issue(db, "OS-A", team=TEAM_A, parent="RFA-1")
    _backlog(db, "OS-A")
    _issue(db, "OS-B", team=TEAM_B, parent="RFA-1")
    _backlog(db, "OS-B")
    _scenario(db, "s-a-q3", team=TEAM_A, year=2026, quarter=3)
    _include(db, "s-a-q3", "OS-A")
    _scenario(db, "s-b-q1", team=TEAM_B, year=2027, quarter=1, name="План Б I кв.")
    _include(db, "s-b-q1", "OS-B")

    progress = multi_team_progress(db, [rfa], today=TODAY)[rfa]

    assert _statuses(progress) == {TEAM_A: NOT_TAKEN, TEAM_B: TAKEN, TEAM_C: NO_EPIC}
    assert [s.label for s in progress.teams[1].scenarios] == ["1 кв. 2027"]


def test_draft_scenario_does_not_count(db_session):
    db = db_session
    _project(db)
    rfa = _rfa(db)
    _issue(db, "OS-A", team=TEAM_A, parent="RFA-1")
    _backlog(db, "OS-A")
    _scenario(db, "s-draft", team=TEAM_A, year=2026, quarter=4, status="draft")
    _include(db, "s-draft", "OS-A")

    progress = multi_team_progress(db, [rfa], today=TODAY)[rfa]

    assert _statuses(progress)[TEAM_A] == NOT_TAKEN
    assert progress.taken == 0


def test_unchecked_allocation_does_not_count(db_session):
    """Эпик есть в утверждённом сценарии, но галочка снята — не взят."""
    db = db_session
    _project(db)
    rfa = _rfa(db)
    _issue(db, "OS-A", team=TEAM_A, parent="RFA-1")
    _backlog(db, "OS-A")
    _scenario(db, "s-a", team=TEAM_A, year=2026, quarter=4)
    _include(db, "s-a", "OS-A", included=False)

    progress = multi_team_progress(db, [rfa], today=TODAY)[rfa]

    assert _statuses(progress)[TEAM_A] == NOT_TAKEN


def test_rfa_own_team_is_participant(db_session):
    """Команда самой RFA — участник, даже если её нет в списке участвующих."""
    db = db_session
    _project(db)
    rfa = _rfa(db, team=TEAM_A, participating=[TEAM_B])
    _issue(db, "OS-B", team=TEAM_B, parent="RFA-1")
    _backlog(db, "OS-B")
    _scenario(db, "s-b", team=TEAM_B, year=2026, quarter=4)
    _include(db, "s-b", "OS-B")

    progress = multi_team_progress(db, [rfa], today=TODAY)[rfa]

    assert [t.team for t in progress.teams] == [TEAM_B, TEAM_A]
    assert _statuses(progress) == {TEAM_B: TAKEN, TEAM_A: NO_EPIC}
    assert (progress.taken, progress.total) == (1, 2)


def test_epic_team_outside_participants_joins(db_session):
    """Команда завела эпик, но в Jira её нет среди участников — всё равно участник."""
    db = db_session
    _project(db)
    rfa = _rfa(db, participating=[TEAM_A, TEAM_B])
    _issue(db, "OS-C", team=TEAM_C, parent="RFA-1")
    _backlog(db, "OS-C")
    _scenario(db, "s-c", team=TEAM_C, year=2026, quarter=4)
    _include(db, "s-c", "OS-C")

    progress = multi_team_progress(db, [rfa], today=TODAY)[rfa]

    assert [t.team for t in progress.teams] == [TEAM_A, TEAM_B, TEAM_C]
    assert _statuses(progress)[TEAM_C] == TAKEN
    assert (progress.taken, progress.total) == (1, 3)


def test_cancelled_epic_is_not_an_epic(db_session):
    """Отменённый эпик команды — как будто эпика нет."""
    db = db_session
    _project(db)
    rfa = _rfa(db, participating=[TEAM_A, TEAM_B])
    _issue(db, "OS-B", team=TEAM_B, parent="RFA-1", status="Отменено")
    _backlog(db, "OS-B")
    # Отменённая команда вне списка участников участником не становится.
    _issue(db, "OS-C", team=TEAM_C, parent="RFA-1", status="Отменено")

    progress = multi_team_progress(db, [rfa], today=TODAY)[rfa]

    assert _statuses(progress) == {TEAM_A: NO_EPIC, TEAM_B: NO_EPIC}


def test_epic_without_team_is_ignored(db_session):
    db = db_session
    _project(db)
    rfa = _rfa(db, participating=[TEAM_A, TEAM_B])
    _issue(db, "OS-X", team=None, parent="RFA-1")

    progress = multi_team_progress(db, [rfa], today=TODAY)[rfa]

    assert _statuses(progress) == {TEAM_A: NO_EPIC, TEAM_B: NO_EPIC}


def test_team_with_two_scenarios_lists_both(db_session):
    """Эпики одной команды в двух утверждённых сценариях — оба в подсказке, по порядку кварталов."""
    db = db_session
    _project(db)
    rfa = _rfa(db, participating=[TEAM_A, TEAM_B])
    for key in ("OS-A1", "OS-A2"):
        _issue(db, key, team=TEAM_A, parent="RFA-1")
        _backlog(db, key)
    _scenario(db, "s-q1", team=TEAM_A, year=2027, quarter=1, name="I кв.")
    _include(db, "s-q1", "OS-A2")
    _scenario(db, "s-q4", team=TEAM_A, year=2026, quarter=4, name="IV кв.")
    _include(db, "s-q4", "OS-A1")

    progress = multi_team_progress(db, [rfa], today=TODAY)[rfa]

    assert [s.name for s in progress.teams[0].scenarios] == ["IV кв.", "I кв."]
    assert progress.taken == 1


def test_single_team_rfa_is_absent(db_session):
    """Не мультикомандная задача — в ответе её нет."""
    db = db_session
    _project(db)
    one = _rfa(db, "RFA-1", team=TEAM_A, participating=[TEAM_A])
    none = _issue(db, "RFA-2", team=TEAM_A, issue_type="Инициатива")

    assert multi_team_progress(db, [one, none, "i-unknown"], today=TODAY) == {}


def test_row_progress_for_rfa_epic_and_plain_row(db_session):
    """Строка RFA и строка её эпика видят одну RFA; своя команда — команда строки."""
    db = db_session
    _project(db)
    rfa = _rfa(db)
    _issue(db, "OS-A", team=TEAM_A, parent="RFA-1")
    _backlog(db, "OS-A")
    _issue(db, "OS-B", team=TEAM_B, parent="RFA-1")
    _backlog(db, "OS-B")
    _scenario(db, "s-a", team=TEAM_A, year=2026, quarter=4)
    _include(db, "s-a", "OS-A")
    plain = _issue(db, "OS-P", team=TEAM_A, issue_type="Задача")

    by_rfa = multi_team_progress(db, [rfa], today=TODAY)

    own = row_progress(by_rfa, issue_id=rfa, parent_id=None, team=TEAM_A)
    epic_b = row_progress(by_rfa, issue_id="i-OS-B", parent_id=rfa, team=TEAM_B)
    assert own is not None and own.rfa is by_rfa[rfa] and own.own_status == TAKEN
    assert epic_b is not None and epic_b.rfa is by_rfa[rfa] and epic_b.own_status == NOT_TAKEN
    assert row_progress(by_rfa, issue_id=plain, parent_id=None, team=TEAM_A) is None


def _count_queries(db, fn) -> int:
    engine = db.get_bind()
    count = 0

    def _hook(*_args, **_kwargs):
        nonlocal count
        count += 1

    event.listen(engine, "before_cursor_execute", _hook)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", _hook)
    return count


def test_query_count_does_not_grow_with_rfas(db_session):
    """Три запроса на любое число RFA — без запроса на каждую."""
    db = db_session
    _project(db)
    _scenario(db, "s-a", team=TEAM_A, year=2026, quarter=4)

    def seed(n: int) -> str:
        rfa = _rfa(db, f"RFA-{n}")
        for team, suffix in ((TEAM_A, "A"), (TEAM_B, "B")):
            _issue(db, f"OS-{n}{suffix}", team=team, parent=f"RFA-{n}")
            _backlog(db, f"OS-{n}{suffix}")
        _include(db, "s-a", f"OS-{n}A")
        return rfa

    ids = [seed(1)]
    db.commit()
    one = _count_queries(db, lambda: multi_team_progress(db, ids, today=TODAY))
    ids += [seed(n) for n in range(2, 12)]
    db.commit()
    many = _count_queries(db, lambda: multi_team_progress(db, ids, today=TODAY))

    assert one == many <= 4
    assert all(p.taken == 1 for p in multi_team_progress(db, ids, today=TODAY).values())


def test_past_quarter_across_year_boundary(db_session):
    """I кв. 2027: утверждённый IV кв. 2026 — уже прошлый, эпик не выполнен — не взят."""
    db = db_session
    _project(db)
    rfa = _rfa(db)
    _epic(db, "OS-A", TEAM_A)
    _scenario(db, "s-a", team=TEAM_A, year=2026, quarter=4)
    _include(db, "s-a", "OS-A")

    progress = multi_team_progress(db, [rfa], today=date(2027, 2, 1))[rfa]

    assert _statuses(progress)[TEAM_A] == NOT_TAKEN
    assert progress.taken == 0


def test_done_epic_counts_with_last_approved_quarter(db_session):
    """Выполненный эпик засчитывается; в подсказке — последний утверждённый квартал,
    где он был. Без утверждённого сценария — просто «выполнен»."""
    db = db_session
    _project(db)
    rfa = _rfa(db)
    _epic(db, "OS-A", TEAM_A, status="ГОТОВО", status_category="done")
    _scenario(db, "s-a-q2", team=TEAM_A, year=2026, quarter=2, name="II кв.")
    _include(db, "s-a-q2", "OS-A")
    _scenario(db, "s-a-q3", team=TEAM_A, year=2026, quarter=3, name="III кв.")
    _include(db, "s-a-q3", "OS-A")
    _epic(db, "OS-B", TEAM_B, status="ГОТОВО", status_category="done")

    progress = multi_team_progress(db, [rfa], today=TODAY)[rfa]

    assert _statuses(progress) == {TEAM_A: DONE, TEAM_B: DONE, TEAM_C: NO_EPIC}
    assert (progress.taken, progress.total) == (2, 3)
    assert [s.label for s in progress.teams[0].scenarios] == ["3 кв. 2026"]
    assert progress.teams[1].scenarios == []


def test_epic_in_current_plan_wins_over_done(db_session):
    """Один эпик команды выполнен, другой в плане IV кв. — команда «взяла» сейчас."""
    db = db_session
    _project(db)
    rfa = _rfa(db)
    _epic(db, "OS-A1", TEAM_A, status="ГОТОВО", status_category="done")
    _epic(db, "OS-A2", TEAM_A)
    _scenario(db, "s-a", team=TEAM_A, year=2026, quarter=4)
    _include(db, "s-a", "OS-A2")

    progress = multi_team_progress(db, [rfa], today=TODAY)[rfa]

    assert _statuses(progress)[TEAM_A] == TAKEN


def test_cancelled_done_epic_is_not_done(db_session):
    """Отменённая задача тоже «закрыта» в Jira, но выполненной не считается."""
    db = db_session
    _project(db)
    rfa = _rfa(db, participating=[TEAM_A, TEAM_B])
    _epic(db, "OS-B", TEAM_B, status="Отменено", status_category="done")

    progress = multi_team_progress(db, [rfa], today=TODAY)[rfa]

    assert _statuses(progress)[TEAM_B] == NO_EPIC


def test_done_leaf_task_is_not_an_epic(db_session):
    """Листовая задача (правило иерархии «не контейнер») под RFA — не эпик:
    её закрытие команду «выполнившей» не делает. Контейнер другого типа — эпик."""
    db = db_session
    _project(db)
    db.add(HierarchyRule(
        priority=100, project_key="OS", issue_type="Задача", require_no_parent=False,
        require_parent=False, is_container=False, is_enabled=True,
    ))
    db.flush()
    rfa = _rfa(db, participating=[TEAM_A, TEAM_B])
    _epic(db, "OS-1", TEAM_A, project="p-os", issue_type="Задача",
          status="ГОТОВО", status_category="done")
    _epic(db, "ITL-1", TEAM_B, issue_type="ИТ-задача", status="Завершен", status_category="done")

    progress = multi_team_progress(db, [rfa], today=TODAY)[rfa]

    assert _statuses(progress) == {TEAM_A: NO_EPIC, TEAM_B: DONE}


def test_scenario_of_other_team_does_not_count(db_session):
    """Эпик переехал в Jira к команде Б, но утверждён в сценарии команды А — у Б не взят."""
    db = db_session
    _project(db)
    rfa = _rfa(db, participating=[TEAM_A, TEAM_B])
    _epic(db, "OS-B", TEAM_B)
    _scenario(db, "s-a", team=TEAM_A, year=2026, quarter=4)
    _include(db, "s-a", "OS-B")

    progress = multi_team_progress(db, [rfa], today=TODAY)[rfa]

    assert _statuses(progress) == {TEAM_A: NO_EPIC, TEAM_B: NOT_TAKEN}


def test_nested_multi_team_row_shows_its_own_rfa(db_session):
    """Мультикомандная задача внутри мультикомандной RFA: для RFA она эпик своей
    команды, а её строка показывает свою плашку — по её собственным эпикам."""
    db = db_session
    _project(db)
    rfa = _rfa(db, participating=[TEAM_A, TEAM_B])
    inner = _issue(db, "ITL-1", team=TEAM_B, parent="RFA-1", issue_type="ИТ-задача",
                   participating=[TEAM_B, TEAM_C])
    _backlog(db, "ITL-1")
    _scenario(db, "s-b", team=TEAM_B, year=2026, quarter=4)
    _include(db, "s-b", "ITL-1")
    _epic(db, "OS-C", TEAM_C, parent="ITL-1")

    by_rfa = multi_team_progress(db, [rfa, inner], today=TODAY)

    assert _statuses(by_rfa[rfa]) == {TEAM_A: NO_EPIC, TEAM_B: TAKEN}
    assert _statuses(by_rfa[inner]) == {TEAM_B: NO_EPIC, TEAM_C: NOT_TAKEN}
    row = row_progress(by_rfa, issue_id=inner, parent_id=rfa, team=TEAM_B)
    assert row is not None and row.rfa is by_rfa[inner] and row.own_status == NO_EPIC
