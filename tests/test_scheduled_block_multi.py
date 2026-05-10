"""ScheduledBlock multi-role / multi-employee — M:N таблицы."""

from datetime import date

from app.models import (
    Employee,
    Role,
    ScheduledBlock,
    ScheduledBlockEmployee,
    ScheduledBlockRole,
)


def test_block_multi_roles_and_employees(db_session):
    role_a = Role(id="r-a", code="analyst", label="Аналитик")
    role_b = Role(id="r-b", code="dev", label="Разработчик")
    emp = Employee(id="e-1", display_name="Иванов", jira_account_id="acc-e1")
    db_session.add_all([role_a, role_b, emp])
    db_session.commit()

    block = ScheduledBlock(
        team="T",
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 5),
        reason="Тренинг",
    )
    block.roles = [
        ScheduledBlockRole(role_id="r-a"),
        ScheduledBlockRole(role_id="r-b"),
    ]
    block.employees = [ScheduledBlockEmployee(employee_id="e-1")]
    db_session.add(block)
    db_session.commit()
    db_session.refresh(block)

    assert {r.role_id for r in block.roles} == {"r-a", "r-b"}
    assert block.employees[0].employee_id == "e-1"


def test_block_no_targets_means_whole_team(db_session):
    """Empty roles + empty employees → block applies to whole team."""
    block = ScheduledBlock(
        team="T2",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 1),
        reason="Закрытие месяца",
    )
    db_session.add(block)
    db_session.commit()
    db_session.refresh(block)
    assert block.roles == []
    assert block.employees == []
