"""Тесты автоматического расширения окна для pinned_start фаз при recompute.

Если после фиксации даты у фазы (`pinned_start=True`) меняются
`hours_allocated`, `involvement` или производственный календарь, то
сохранённый `end_date` может перестать вмещать запланированные часы.
`compute_schedule` обязан пере-вывести `end_date` + `daily_hours_json`
через тот же хелпер `_extend_window_for_hours`, что используется в
drag-pin entry point — старт остаётся зафиксированным.
"""

import json
import uuid
from datetime import date, datetime

import pytest

from app.models import (
    BacklogItem,
    Employee,
    PlanningScenario,
    ResourcePlan,
    ResourcePlanAssignment,
    ScenarioAllocation,
)
from app.models.employee_team import EmployeeTeam
from app.services.resource_planning_service import ResourcePlanningService


@pytest.fixture
def seed_pinned_dev(db_session):
    """Pinned dev-фаза на 40h, инициатива с estimate_dev_hours=40 и developer."""
    team = "T_EXT"

    dev = Employee(
        jira_account_id=uuid.uuid4().hex[:16],
        display_name="Dev-extend",
        team=team,
        is_active=True,
        role="developer",
    )
    db_session.add(dev)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=dev.id, team=team, is_primary=True))

    item = BacklogItem(
        title="ext-pin-test",
        priority=1,
        estimate_dev_hours=30.0,
        involvement_dev=1.0,
    )
    db_session.add(item)
    db_session.flush()

    scenario = PlanningScenario(
        name="ext-scenario",
        quarter="Q2",
        year=2026,
        status="draft",
        team=team,
    )
    db_session.add(scenario)
    db_session.flush()
    db_session.add(
        ScenarioAllocation(
            scenario_id=scenario.id,
            backlog_item_id=item.id,
            included_flag=True,
        )
    )

    plan = ResourcePlan(
        team=team,
        quarter="Q2",
        year=2026,
        status="draft",
        scenario_id=scenario.id,
    )
    db_session.add(plan)
    db_session.commit()

    return {"plan": plan, "item": item, "dev": dev}


def test_compute_schedule_extends_pinned_start_window(db_session, seed_pinned_dev):
    """При снижении involvement после пина — end_date авто-расширяется.

    Стартовый сценарий: pinned dev-фаза 30h, 5 рабочих дней (Mon 20.04..Fri 24.04)
    при involvement=1.0 (cap 6h/день). Затем involvement понижается до 0.6
    (cap 3.6h/день). На 30h теперь нужно ceil(30 / 3.6) = 9 рабочих дней.
    От Mon 20.04.2026: 20,21,22,23,24 (5), 27,28,29,30 (9) — конец Thu 30.04.2026.

    Производственный календарь в тесте не сидим — хелпер падает на
    weekday-only логику (Mon-Fri = 6h, Sat/Sun = 0). Начальная раскладка
    6h × 5 дней = 30h помещается в дневной cap (6h/день), поэтому
    RcpspLeveler не сдвигает фазу из-за overload до того, как наш патч
    пере-вычислит окно.
    """
    plan = seed_pinned_dev["plan"]
    item = seed_pinned_dev["item"]
    dev = seed_pinned_dev["dev"]

    fixed_start = date(2026, 4, 20)
    initial_end = date(2026, 4, 24)
    # Изначальная раскладка 5 рабочих дней × 6h = 30h (в пределах cap=6h).
    # Хелпер должен её ЗАМЕНИТЬ на 9-дневную, а не дополнить.
    initial_daily = json.dumps(
        {
            "2026-04-20": 6.0,
            "2026-04-21": 6.0,
            "2026-04-22": 6.0,
            "2026-04-23": 6.0,
            "2026-04-24": 6.0,
        }
    )
    a = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item.id,
        phase="dev",
        employee_id=dev.id,
        part_number=1,
        hours_allocated=30.0,
        start_date=fixed_start,
        end_date=initial_end,
        pinned_start=True,
        manual_edit_at=datetime.utcnow(),
        daily_hours_json=initial_daily,
    )
    db_session.add(a)
    db_session.commit()
    assignment_id = a.id

    # Понижаем involvement_dev → пере-расчёт должен расширить окно.
    item.involvement_dev = 0.6
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan.id)

    db_session.expire_all()
    a2 = db_session.get(ResourcePlanAssignment, assignment_id)
    assert a2 is not None
    assert a2.pinned_start is True, "pinned_start должен оставаться True"
    assert a2.start_date == fixed_start, "start_date НЕ трогаем — он зафиксирован"
    assert a2.end_date == date(2026, 4, 30), (
        f"end_date должен расшириться до Thu 30.04.2026; получили {a2.end_date}"
    )
    assert a2.daily_hours_json is not None
    daily = json.loads(a2.daily_hours_json)
    # Сумма должна равняться hours_allocated.
    assert abs(sum(daily.values()) - 30.0) < 0.01
    # Старая 5-дневная раскладка должна быть заменена на 9-дневную.
    assert len(daily) == 9
    assert "2026-04-30" in daily
    # out_of_quarter: Q2 2026 заканчивается 30.06; 30.04 < 30.06.
    assert a2.out_of_quarter is False


def test_compute_schedule_non_pinned_unaffected(db_session, seed_pinned_dev):
    """Sanity: фазы без pinned_start пересчитываются нормально (старая логика).

    Сидим dev-фазу без pin-флагов и без daily_hours_json. После
    compute_schedule аллокатор должен заполнить end_date/daily_hours_json.
    """
    plan = seed_pinned_dev["plan"]

    ResourcePlanningService(db_session).compute_schedule(plan.id)

    rows = (
        db_session.query(ResourcePlanAssignment)
        .filter(
            ResourcePlanAssignment.plan_id == plan.id,
            ResourcePlanAssignment.phase == "dev",
        )
        .all()
    )
    # Аллокатор должен создать хотя бы одну dev-строку.
    assert len(rows) >= 1
    for r in rows:
        assert r.pinned_start is False
        assert r.start_date is not None
        assert r.end_date is not None
        assert r.end_date >= r.start_date
