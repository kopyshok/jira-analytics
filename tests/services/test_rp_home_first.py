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


def test_home_plan_avoids_booking_of_shared_member(db_session):
    """E состоит и в A, и в B: план A обходит часы E в плане B."""
    e = make_employee(db_session, "Шутов", "A")
    join_team(db_session, e, "B")
    sc_b, plan_b = make_plan(db_session, "B")
    book(db_session, plan_b, add_item(db_session, sc_b, "Работа B", dev=12), e,
         {"2026-01-01": 6.0, "2026-01-02": 6.0})
    sc_a, plan_a = make_plan(db_session, "A", plan_status="draft")
    add_item(db_session, sc_a, "Работа A", dev=12)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan_a.id)

    assert _dev_days(db_session, plan_a.id) == {"2026-01-05", "2026-01-06"}


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
