"""Периоды участия в команде — модель и helper."""

from datetime import date

from app.models import Employee, EmployeeTeam
from app.services import team_membership as tm


def _emp(db, name="Иванов И.", account="acc-1", role="dev"):
    e = Employee(
        jira_account_id=account,
        display_name=name,
        is_active=True,
        role=role,
    )
    db.add(e)
    db.flush()
    return e


def test_membership_stores_left_at(db_session):
    """У участия можно задать дату выбытия."""
    emp = _emp(db_session)
    db_session.add(EmployeeTeam(
        employee_id=emp.id,
        team="Альфа",
        is_primary=True,
        joined_at=date(2026, 1, 1),
        left_at=date(2026, 2, 15),
    ))
    db_session.commit()

    row = db_session.query(EmployeeTeam).one()
    assert row.left_at == date(2026, 2, 15)


def test_two_periods_in_same_team_allowed(db_session):
    """Ушёл и вернулся — две записи по одной паре сотрудник/команда."""
    emp = _emp(db_session)
    db_session.add_all([
        EmployeeTeam(
            employee_id=emp.id, team="Альфа", is_primary=False,
            joined_at=date(2026, 1, 1), left_at=date(2026, 3, 1),
        ),
        EmployeeTeam(
            employee_id=emp.id, team="Альфа", is_primary=True,
            joined_at=date(2026, 9, 1), left_at=None,
        ),
    ])
    db_session.commit()

    rows = db_session.query(EmployeeTeam).filter_by(team="Альфа").all()
    assert len(rows) == 2


def _membership(db, emp, team, joined=None, left=None, primary=False):
    row = EmployeeTeam(
        employee_id=emp.id, team=team, is_primary=primary,
        joined_at=joined, left_at=left,
    )
    db.add(row)
    db.flush()
    return row


def test_members_on_respects_bounds(db_session):
    """left_at — первый день вне команды."""
    emp = _emp(db_session)
    _membership(db_session, emp, "Альфа", date(2026, 1, 1), date(2026, 2, 15))
    db_session.commit()

    assert tm.members_on(db_session, ["Альфа"], date(2026, 2, 14)) == {emp.id}
    assert tm.members_on(db_session, ["Альфа"], date(2026, 2, 15)) == set()
    assert tm.members_on(db_session, ["Альфа"], date(2025, 12, 31)) == set()


def test_members_on_open_bounds(db_session):
    """Пустые даты — открытые границы."""
    emp = _emp(db_session)
    _membership(db_session, emp, "Альфа")
    db_session.commit()

    assert tm.members_on(db_session, ["Альфа"], date(2020, 1, 1)) == {emp.id}
    assert tm.members_on(db_session, ["Альфа"], date(2030, 1, 1)) == {emp.id}


def test_members_overlapping(db_session):
    """Пересечение с периодом — хотя бы один день."""
    emp = _emp(db_session)
    _membership(db_session, emp, "Альфа", date(2026, 1, 1), date(2026, 2, 15))
    db_session.commit()

    assert tm.members_overlapping(
        db_session, ["Альфа"], date(2026, 1, 1), date(2026, 3, 31)
    ) == {emp.id}
    assert tm.members_overlapping(
        db_session, ["Альфа"], date(2026, 3, 1), date(2026, 3, 31)
    ) == set()


def test_member_intervals_clips_to_period(db_session):
    """Отрезки обрезаются границами запрошенного периода."""
    emp = _emp(db_session)
    _membership(db_session, emp, "Альфа", date(2026, 1, 10), date(2026, 2, 15))
    db_session.commit()

    intervals = tm.member_intervals(
        db_session, ["Альфа"], date(2026, 1, 1), date(2026, 3, 31)
    )
    assert intervals[emp.id] == [(date(2026, 1, 10), date(2026, 2, 14))]


def test_member_intervals_two_periods(db_session):
    """Два периода с разрывом — два отрезка."""
    emp = _emp(db_session)
    _membership(db_session, emp, "Альфа", date(2026, 1, 1), date(2026, 2, 1))
    _membership(db_session, emp, "Альфа", date(2026, 3, 1), None)
    db_session.commit()

    intervals = tm.member_intervals(
        db_session, ["Альфа"], date(2026, 1, 1), date(2026, 3, 31)
    )
    assert intervals[emp.id] == [
        (date(2026, 1, 1), date(2026, 1, 31)),
        (date(2026, 3, 1), date(2026, 3, 31)),
    ]


def test_day_in_intervals():
    """Проверка одного дня по заранее вычисленным отрезкам."""
    intervals = [(date(2026, 1, 1), date(2026, 1, 31))]
    assert tm.day_in_intervals(date(2026, 1, 15), intervals) is True
    assert tm.day_in_intervals(date(2026, 2, 1), intervals) is False


def test_members_ever_includes_departed(db_session):
    """Выбывшие входят в «когда-либо состоял»."""
    emp = _emp(db_session)
    _membership(db_session, emp, "Альфа", date(2020, 1, 1), date(2021, 1, 1))
    db_session.commit()

    assert tm.members_ever(db_session, ["Альфа"]) == {emp.id}
    assert tm.members_on(db_session, ["Альфа"], date(2026, 1, 1)) == set()


def test_primary_team_on(db_session):
    """Основная команда определяется на дату."""
    emp = _emp(db_session)
    _membership(db_session, emp, "Альфа", date(2026, 1, 1), date(2026, 2, 15), primary=True)
    _membership(db_session, emp, "Бета", date(2026, 2, 15), None, primary=True)
    db_session.commit()

    assert tm.primary_team_on(db_session, emp.id, date(2026, 1, 20)) == "Альфа"
    assert tm.primary_team_on(db_session, emp.id, date(2026, 3, 1)) == "Бета"


def test_shared_members(db_session):
    """Сотрудник в двух командах за период — общий."""
    emp = _emp(db_session)
    _membership(db_session, emp, "Альфа", primary=True)
    _membership(db_session, emp, "Бета")
    solo = _emp(db_session, name="Петров П.", account="acc-2")
    _membership(db_session, solo, "Альфа")
    db_session.commit()

    shared = tm.shared_members(
        db_session, ["Альфа"], date(2026, 1, 1), date(2026, 3, 31)
    )
    assert shared == {emp.id: ["Бета"]}
