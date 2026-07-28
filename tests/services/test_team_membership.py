"""Периоды участия в команде — модель и helper."""

from datetime import date

from app.models import Employee, EmployeeTeam


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
