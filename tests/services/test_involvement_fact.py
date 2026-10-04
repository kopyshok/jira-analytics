"""Фактическая вовлечённость: доля проектных часов в списаниях.

Квартал — III 2026. Производственного календаря в базе нет, поэтому норма —
8 ч по будням: июль 184 ч (23 дня), август 168 ч (21), сентябрь 176 ч (22).
"""

from datetime import date, datetime
from itertools import count
from typing import Optional

import pytest
from sqlalchemy import event

from app.models import (
    Absence,
    AbsenceReason,
    Category,
    Employee,
    EmployeeTeam,
    Issue,
    MandatoryWorkType,
    Project,
    Worklog,
)
from app.services.categories import get_category_work_types
from app.services.involvement_fact import last_completed_quarter, team_facts

_seq = count(1)


@pytest.fixture
def world(db_session):
    """Виды работ, категории и по задаче на каждый случай."""
    project_wt = MandatoryWorkType(code="project", label="Проекты и развитие")
    support_wt = MandatoryWorkType(code="support_consult", label="Сопровождение")
    db_session.add_all([project_wt, support_wt])
    db_session.flush()
    db_session.add_all([
        Category(code="quarterly_tasks", label="Квартальные задачи", work_type_id=project_wt.id),
        Category(code="support_consultation", label="Сопровождение", work_type_id=support_wt.id),
        Category(code="unfilled_worklog", label="Незаполненные"),
    ])
    proj = Project(jira_project_id="p1", key="PRJ", name="Проект")
    db_session.add(proj)
    db_session.flush()

    def issue(category: Optional[str], included: bool = True) -> Issue:
        n = next(_seq)
        it = Issue(
            jira_issue_id=f"i{n}", key=f"PRJ-{n}", project_id=proj.id,
            summary="Задача", issue_type="Task", status="В работе",
            category=category, include_in_analysis=included,
        )
        db_session.add(it)
        db_session.flush()
        return it

    db_session.commit()
    return {
        "project": issue("quarterly_tasks"),
        "support": issue("support_consultation"),
        "unmapped": issue("unfilled_worklog"),
        "none": issue(None),
        "excluded": issue("quarterly_tasks", included=False),
    }


def _employee(db, name: str, role: Optional[str], *, active: bool = True) -> Employee:
    emp = Employee(
        jira_account_id=f"acc-{next(_seq)}", display_name=name, role=role, is_active=active,
    )
    db.add(emp)
    db.flush()
    return emp


def _member(db, emp: Employee, team: str, joined: Optional[date] = None,
            left: Optional[date] = None) -> None:
    db.add(EmployeeTeam(
        employee_id=emp.id, team=team, is_primary=True, joined_at=joined, left_at=left,
    ))
    db.flush()


def _log(db, emp: Employee, issue: Issue, day: date, hours: float) -> None:
    """Списание; ``day`` без времени — 10:00 этого дня."""
    started = day if isinstance(day, datetime) else datetime(day.year, day.month, day.day, 10, 0)
    db.add(Worklog(
        jira_worklog_id=f"w{next(_seq)}", issue_id=issue.id, employee_id=emp.id,
        started_at=started,
        hours=hours, time_spent_seconds=int(hours * 3600),
    ))
    db.flush()


def _team(result, name):
    return next(t for t in result if t.team == name)


def _person(team, name):
    return next(p for p in team.people if p.name == name)


def _role(team, role):
    return next(r for r in team.roles if r.role == role)


def test_category_work_types_only_mapped(db_session, world):
    """Карта «категория → вид работ» без категорий, у которых вид не задан."""
    mapping = get_category_work_types(db_session)
    assert set(mapping) == {"quarterly_tasks", "support_consultation"}


def test_fact_and_logged_of_norm_by_month(db_session, world):
    """Факт = проектные ÷ все списанные; «списано от нормы» = все ÷ норма."""
    an = _employee(db_session, "Аналитикова", "analyst")
    _member(db_session, an, "Альфа")
    _log(db_session, an, world["project"], date(2026, 7, 6), 60)
    _log(db_session, an, world["support"], date(2026, 7, 7), 20)
    _log(db_session, an, world["project"], date(2026, 8, 3), 30)
    _log(db_session, an, world["none"], date(2026, 8, 4), 6)
    _log(db_session, an, world["unmapped"], date(2026, 8, 5), 4)
    db_session.commit()

    person = _person(_team(team_facts(db_session, ["Альфа"], 2026, 3), "Альфа"), "Аналитикова")
    assert person.role == "analyst"
    jul, aug, sep = person.months[7], person.months[8], person.months[9]
    assert (jul.project_hours, jul.logged_hours, jul.norm_hours) == (60, 80, 184)
    assert jul.fact == pytest.approx(0.75)
    assert jul.logged_of_norm == pytest.approx(80 / 184)
    assert aug.fact == pytest.approx(0.75)
    assert sep.fact is None
    assert sep.logged_of_norm == 0.0
    assert person.total.fact == pytest.approx(90 / 120)
    assert person.total.logged_of_norm == pytest.approx(120 / 528)


def test_excluded_from_analysis_not_counted(db_session, world):
    """Задача, исключённая из анализа, не попадает ни в проектные, ни во все часы."""
    dev = _employee(db_session, "Разработчиков", "dev")
    _member(db_session, dev, "Альфа")
    _log(db_session, dev, world["project"], date(2026, 7, 6), 8)
    _log(db_session, dev, world["excluded"], date(2026, 7, 7), 8)
    db_session.commit()

    person = _person(_team(team_facts(db_session, ["Альфа"], 2026, 3), "Альфа"), "Разработчиков")
    assert person.total.logged_hours == 8
    assert person.total.fact == pytest.approx(1.0)


def test_role_average_is_ratio_of_sums(db_session, world):
    """Среднее по роли — Σ проектных ÷ Σ всех, а не среднее процентов людей."""
    d1 = _employee(db_session, "Первый", "dev")
    d2 = _employee(db_session, "Второй", "dev")
    for d in (d1, d2):
        _member(db_session, d, "Альфа")
    _log(db_session, d1, world["project"], date(2026, 7, 6), 10)
    _log(db_session, d2, world["support"], date(2026, 7, 6), 30)
    db_session.commit()

    team = _team(team_facts(db_session, ["Альфа"], 2026, 3), "Альфа")
    dev = _role(team, "dev")
    assert dev.people == 2
    assert dev.total.fact == pytest.approx(10 / 40)
    assert dev.months[7].fact == pytest.approx(10 / 40)
    assert dev.total.norm_hours == 2 * 528
    assert [r.role for r in team.roles] == ["dev"]


def test_team_by_worklog_date(db_session, world):
    """После перевода часы и норма уходят в новую команду."""
    an = _employee(db_session, "Переведённая", "analyst")
    _member(db_session, an, "Альфа", left=date(2026, 8, 1))
    _member(db_session, an, "Бета", joined=date(2026, 8, 1))
    _log(db_session, an, world["project"], date(2026, 7, 6), 10)
    _log(db_session, an, world["support"], date(2026, 8, 3), 10)
    db_session.commit()

    result = team_facts(db_session, ["Альфа", "Бета"], 2026, 3)
    alpha = _person(_team(result, "Альфа"), "Переведённая")
    beta = _person(_team(result, "Бета"), "Переведённая")
    assert (alpha.total.project_hours, alpha.total.logged_hours) == (10, 10)
    assert alpha.total.norm_hours == 184
    assert alpha.months[8].norm_hours == 0
    assert (beta.total.project_hours, beta.total.logged_hours) == (0, 10)
    assert beta.total.norm_hours == 168 + 176


def test_only_analysts_and_developers(db_session, world):
    """Тестировщик, РП и сотрудник без роли в отчёт не попадают."""
    for name, role in (("Тестер", "qa"), ("Безролевой", None), ("Руководитель", "RP")):
        emp = _employee(db_session, name, role)
        _member(db_session, emp, "Альфа")
        _log(db_session, emp, world["project"], date(2026, 7, 6), 8)
    an = _employee(db_session, "Аналитик", "analyst")
    _member(db_session, an, "Альфа")
    _log(db_session, an, world["project"], date(2026, 7, 6), 8)
    db_session.commit()

    team = _team(team_facts(db_session, ["Альфа"], 2026, 3), "Альфа")
    assert [p.name for p in team.people] == ["Аналитик"]
    assert [r.role for r in team.roles] == ["analyst"]


def test_absence_reduces_norm(db_session, world):
    """Отпуск 6–10 июля (5 будней) вычитается из нормы."""
    dev = _employee(db_session, "Отпускник", "dev")
    _member(db_session, dev, "Альфа")
    reason = AbsenceReason(code="vacation", label="Отпуск")
    db_session.add(reason)
    db_session.flush()
    db_session.add(Absence(
        employee_id=dev.id, start_date=date(2026, 7, 6), end_date=date(2026, 7, 10),
        reason_id=reason.id,
    ))
    _log(db_session, dev, world["project"], date(2026, 7, 13), 8)
    db_session.commit()

    person = _person(_team(team_facts(db_session, ["Альфа"], 2026, 3), "Альфа"), "Отпускник")
    assert person.months[7].norm_hours == 184 - 40


def test_member_without_worklogs(db_session, world):
    """Работающий без списаний — в отчёте с пустым фактом; уволенный без списаний — нет."""
    active = _employee(db_session, "Молчун", "dev")
    gone = _employee(db_session, "Ушедший", "dev", active=False)
    for emp in (active, gone):
        _member(db_session, emp, "Альфа")
    db_session.commit()

    team = _team(team_facts(db_session, ["Альфа"], 2026, 3), "Альфа")
    assert [p.name for p in team.people] == ["Молчун"]
    person = team.people[0]
    assert person.total.fact is None
    assert person.total.logged_of_norm == 0.0
    assert _role(team, "dev").total.fact is None


def test_deactivated_with_worklogs_excluded(db_session, world):
    """Выключенный сотрудник не учитывается нигде — даже со списаниями за квартал."""
    gone = _employee(db_session, "Выключенный", "dev", active=False)
    stay = _employee(db_session, "Работающий", "dev")
    for emp in (gone, stay):
        _member(db_session, emp, "Альфа")
    _log(db_session, gone, world["support"], date(2026, 7, 6), 40)
    _log(db_session, stay, world["project"], date(2026, 7, 6), 8)
    db_session.commit()

    team = _team(team_facts(db_session, ["Альфа"], 2026, 3), "Альфа")
    assert [p.name for p in team.people] == ["Работающий"]
    assert _role(team, "dev").people == 1
    assert _role(team, "dev").total.fact == pytest.approx(1.0)


def test_running_quarter_counts_to_today(db_session, world):
    """Идущий квартал — по сегодня: норма и списания после сегодня не считаются,
    месяцы целиком в будущем пустые."""
    dev = _employee(db_session, "Текущий", "dev")
    _member(db_session, dev, "Альфа")
    _log(db_session, dev, world["project"], date(2026, 10, 1), 8)
    _log(db_session, dev, world["support"], date(2026, 10, 2), 8)
    _log(db_session, dev, world["support"], date(2026, 11, 10), 8)  # будущее
    db_session.commit()

    person = _person(
        _team(team_facts(db_session, ["Альфа"], 2026, 4, today=date(2026, 10, 4)), "Альфа"),
        "Текущий",
    )
    oct_, nov, dec = person.months[10], person.months[11], person.months[12]
    # 1–2 октября — будни, 3–4 — выходные.
    assert (oct_.norm_hours, oct_.logged_hours) == (16, 16)
    assert oct_.logged_of_norm == pytest.approx(1.0)
    assert oct_.fact == pytest.approx(0.5)
    for m in (nov, dec):
        assert (m.norm_hours, m.logged_hours) == (0, 0)
        assert m.fact is None and m.logged_of_norm is None
    assert person.total.logged_of_norm == pytest.approx(1.0)


def test_join_and_leave_day_boundaries(db_session, world):
    """День выхода (``left_at``) — уже не в старой команде; день входа — в новой."""
    an = _employee(db_session, "Граница", "analyst")
    _member(db_session, an, "Альфа", left=date(2026, 8, 3))
    _member(db_session, an, "Бета", joined=date(2026, 8, 3))
    _log(db_session, an, world["project"], date(2026, 7, 31), 8)
    _log(db_session, an, world["support"], datetime(2026, 8, 3, 0, 0), 4)
    db_session.commit()

    result = team_facts(db_session, ["Альфа", "Бета"], 2026, 3)
    alpha = _person(_team(result, "Альфа"), "Граница")
    beta = _person(_team(result, "Бета"), "Граница")
    assert (alpha.total.logged_hours, alpha.total.project_hours) == (8, 8)
    assert (beta.total.logged_hours, beta.total.project_hours) == (4, 0)


def test_quarter_edge_by_time(db_session, world):
    """30.09 23:30 — III квартал, 01.10 00:00 — уже IV."""
    dev = _employee(db_session, "Полуночник", "dev")
    _member(db_session, dev, "Альфа")
    _log(db_session, dev, world["project"], datetime(2026, 9, 30, 23, 30), 2)
    _log(db_session, dev, world["support"], datetime(2026, 10, 1, 0, 0), 3)
    db_session.commit()

    q3 = _person(_team(team_facts(db_session, ["Альфа"], 2026, 3), "Альфа"), "Полуночник")
    assert (q3.months[9].logged_hours, q3.total.logged_hours) == (2, 2)
    q4 = _person(
        _team(team_facts(db_session, ["Альфа"], 2026, 4, today=date(2026, 12, 31)), "Альфа"),
        "Полуночник",
    )
    assert (q4.months[10].logged_hours, q4.total.logged_hours) == (3, 3)


def test_two_teams_same_day(db_session, world):
    """Состоит в двух командах в один день — списание идёт в обе."""
    dev = _employee(db_session, "Общий", "dev")
    _member(db_session, dev, "Альфа")
    db_session.add(EmployeeTeam(employee_id=dev.id, team="Бета", is_primary=False))
    _log(db_session, dev, world["project"], date(2026, 7, 6), 8)
    db_session.commit()

    result = team_facts(db_session, ["Альфа", "Бета"], 2026, 3)
    for name in ("Альфа", "Бета"):
        person = _person(_team(result, name), "Общий")
        assert person.total.logged_hours == 8
        assert person.total.norm_hours == 528


def test_unknown_team_is_empty(db_session, world):
    """Команда без людей — пустой блок, а не ошибка."""
    [team] = team_facts(db_session, ["Пустая"], 2026, 3)
    assert team.team == "Пустая"
    assert team.people == [] and team.roles == []


def test_query_count_does_not_grow_with_people(db_session, world, engine):
    """Один проход по списаниям: число обращений к базе не зависит от числа людей."""

    def add_people(n: int) -> None:
        for _ in range(n):
            emp = _employee(db_session, f"Человек {next(_seq)}", "dev")
            _member(db_session, emp, "Альфа")
            _log(db_session, emp, world["project"], date(2026, 7, 6), 8)
            _log(db_session, emp, world["support"], date(2026, 8, 6), 8)
        db_session.commit()

    def queries() -> int:
        calls = []

        def _count(*_args, **_kw):
            calls.append(1)

        event.listen(engine, "before_cursor_execute", _count)
        try:
            team_facts(db_session, ["Альфа"], 2026, 3)
        finally:
            event.remove(engine, "before_cursor_execute", _count)
        return len(calls)

    add_people(1)
    one = queries()
    add_people(5)
    assert queries() == one


@pytest.mark.parametrize(
    "today, expected",
    [
        (date(2026, 10, 4), (2026, 3)),
        (date(2026, 7, 1), (2026, 2)),
        (date(2026, 1, 15), (2025, 4)),
        (date(2026, 3, 31), (2025, 4)),
    ],
)
def test_last_completed_quarter(today, expected):
    assert last_completed_quarter(today) == expected
