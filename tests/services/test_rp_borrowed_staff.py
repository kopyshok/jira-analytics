"""Привлечение сотрудников из чужих команд в ресурсный план."""

from datetime import date

from app.services.resource_planning_service import ResourcePlanningService
from tests.services.xteam_factory import make_employee

D = date.fromisoformat


def test_borrowed_employee_is_available_outside_plan_team(db_session):
    e = make_employee(db_session, "Чужой", "A")
    db_session.commit()
    svc = ResourcePlanningService(db_session)

    plain = svc.build_availability([e], D("2026-01-05"), D("2026-01-05"), [], team="B")
    borrowed = svc.build_availability(
        [e], D("2026-01-05"), D("2026-01-05"), [], team="B", borrowed={e.id}
    )

    assert plain[e.id][D("2026-01-05")] == 0.0
    assert borrowed[e.id][D("2026-01-05")] == 6.0
