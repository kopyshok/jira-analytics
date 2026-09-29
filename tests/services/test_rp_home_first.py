"""Правило «сначала домашняя команда»: чьи брони обходит расчёт плана."""

import json

from sqlalchemy import select

from app.models import ResourcePlanAssignment
from app.services.resource_planning_service import ResourcePlanningService
from tests.services.xteam_factory import (
    add_item, book, join_team, make_employee, make_issue, make_plan,
)


def _dev_days(db, plan_id):
    rows = db.execute(
        select(ResourcePlanAssignment).where(
            ResourcePlanAssignment.plan_id == plan_id,
            ResourcePlanAssignment.phase == "dev",
        )
    ).scalars().all()
    return {k for r in rows for k, v in json.loads(r.daily_hours_json or "{}").items() if v > 0}


def _booked_in(db_session, team, e):
    """Опорный план ``team`` занял E на 01.01 и 02.01."""
    sc, plan = make_plan(db_session, team)
    book(db_session, plan, add_item(db_session, sc, f"Работа {team}", dev=12), e,
         {"2026-01-01": 6.0, "2026-01-02": 6.0})


def _computed_days(db_session, team):
    sc, plan = make_plan(db_session, team, plan_status="draft")
    add_item(db_session, sc, "Своя работа", dev=12)
    db_session.commit()
    ResourcePlanningService(db_session).compute_schedule(plan.id)
    return _dev_days(db_session, plan.id)


def test_primary_team_plan_ignores_booking_of_secondary_team(db_session):
    """E в A (основная) и в B: основная команда не уступает — план A берёт
    дни, занятые в плане B, а подстраиваться будет B."""
    e = make_employee(db_session, "Шутов", "A")
    join_team(db_session, e, "B")
    _booked_in(db_session, "B", e)

    assert _computed_days(db_session, "A") == {"2026-01-01", "2026-01-02"}


def test_secondary_team_plan_avoids_booking_of_primary_team(db_session):
    e = make_employee(db_session, "Шутов", "A")
    join_team(db_session, e, "B")
    _booked_in(db_session, "A", e)

    assert _computed_days(db_session, "B") == {"2026-01-05", "2026-01-06"}


def test_secondary_team_plan_avoids_other_secondary_team(db_session):
    """Две не основные команды уступают друг другу, как равные."""
    e = make_employee(db_session, "Шутов", "A")
    join_team(db_session, e, "B")
    join_team(db_session, e, "C")
    _booked_in(db_session, "C", e)

    assert _computed_days(db_session, "B") == {"2026-01-05", "2026-01-06"}


def test_member_teams_without_primary_avoid_each_other(db_session):
    """Основной команды нет — все его команды равны и обходят брони друг друга."""
    e = make_employee(db_session, "Шутов", "A", member=False)
    join_team(db_session, e, "A")
    join_team(db_session, e, "B")
    _booked_in(db_session, "B", e)

    assert _computed_days(db_session, "A") == {"2026-01-05", "2026-01-06"}


def test_borrower_avoids_every_other_team(db_session, sample_project):
    """Привлечённый в план B обходит брони всех команд: и домашней A,
    и команды C, которая тоже его привлекла."""
    e = make_employee(db_session, "Пряничников", "A", jira_account_id="acc-e")
    make_employee(db_session, "Свой B", "B")
    sc_a, plan_a = make_plan(db_session, "A")
    book(db_session, plan_a, add_item(db_session, sc_a, "Работа A", dev=6), e,
         {"2026-01-01": 6.0})
    sc_c, plan_c = make_plan(db_session, "C")
    book(db_session, plan_c, add_item(db_session, sc_c, "Работа C", dev=6), e,
         {"2026-01-02": 6.0})
    issue = make_issue(db_session, sample_project, "OS-10", developer="acc-e")
    sc_b, plan_b = make_plan(db_session, "B", plan_status="draft")
    add_item(db_session, sc_b, "Работа B", dev=12, issue=issue)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan_b.id)

    assert _dev_days(db_session, plan_b.id) == {"2026-01-05", "2026-01-06"}
