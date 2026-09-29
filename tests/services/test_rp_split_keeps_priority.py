"""Раздробленная фаза: место в очереди приоритета и параллельные ветки.

Воспроизводит OS-91446: анализ задачи с высшим приоритетом раздроблен на
две части с каскадом на разработку и тестирование.

1. При пересчёте части раздробленной фазы раскладывались отдельным проходом
   ПОСЛЕ всех остальных задач — на остатки ёмкости. Задача уезжала за задачи
   с меньшим приоритетом (в декабрь), а при следующих пересчётах уже не могла
   вернуться раньше своей прежней даты.
2. Связи частей шли не ветками: первая часть разработки ждала обе части
   анализа, части тестирования цеплялись к частям анализа и к последней
   части разработки. Ветка K — это анализ K → разработка K → тестирование K.
"""

import uuid
from datetime import date, timedelta

from sqlalchemy import select

from app.models import (
    BacklogItem,
    PhasePredecessor,
    Employee,
    PlanningScenario,
    ResourcePlan,
    ResourcePlanAssignment,
    ScenarioAllocation,
)
from app.models.employee_team import EmployeeTeam
from app.services.resource_planning_service import ResourcePlanningService


def _emp(db_session, team: str, role: str) -> Employee:
    e = Employee(
        jira_account_id=uuid.uuid4().hex[:16],
        display_name=f"{role}-{team}",
        team=team,
        is_active=True,
        role=role,
    )
    db_session.add(e)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=e.id, team=team, is_primary=True))
    return e


def _next_working_day(d: date) -> date:
    nxt = d + timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    return nxt


def _rows(db_session, plan_id: str, item_id: str, phase: str):
    return (
        db_session.execute(
            select(ResourcePlanAssignment)
            .where(
                ResourcePlanAssignment.plan_id == plan_id,
                ResourcePlanAssignment.backlog_item_id == item_id,
                ResourcePlanAssignment.phase == phase,
            )
            .order_by(ResourcePlanAssignment.part_number)
        )
        .scalars()
        .all()
    )


def _plan(db_session, team: str, items) -> ResourcePlan:
    _emp(db_session, team, "analyst")
    _emp(db_session, team, "developer")
    db_session.add_all(items)
    db_session.flush()
    scenario = PlanningScenario(
        name=team, quarter="Q4", year=2026, status="draft", team=team,
    )
    db_session.add(scenario)
    db_session.flush()
    for it in items:
        db_session.add(
            ScenarioAllocation(
                scenario_id=scenario.id, backlog_item_id=it.id, included_flag=True,
            )
        )
    plan = ResourcePlan(
        team=team, quarter="Q4", year=2026, status="draft",
        scenario_id=scenario.id,
    )
    db_session.add(plan)
    db_session.commit()
    return plan


def test_split_phase_keeps_priority_order(db_session):
    top = BacklogItem(
        title="top", priority=9,
        estimate_analyst_hours=40.0, estimate_dev_hours=40.0,
    )
    low = BacklogItem(
        title="low", priority=3,
        estimate_analyst_hours=80.0, estimate_dev_hours=40.0,
    )
    plan = _plan(db_session, "T_SPLIT_PRIORITY", [top, low])

    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(plan.id)

    top_an = _rows(db_session, plan.id, top.id, "analyst")
    low_an = _rows(db_session, plan.id, low.id, "analyst")
    assert top_an[0].start_date < low_an[0].start_date
    q_start = top_an[0].start_date

    svc.split_assignment(top_an[0].id, [20.0, 20.0], cascade=True)
    db_session.commit()

    # Два пересчёта подряд: второй ловит «храповик» — раньше часть не могла
    # встать раньше даты, полученной прошлым пересчётом.
    for _ in range(2):
        svc.compute_schedule(plan.id)
        db_session.expire_all()

        parts = _rows(db_session, plan.id, top.id, "analyst")
        low_an = _rows(db_session, plan.id, low.id, "analyst")
        assert len(parts) == 2
        assert parts[0].start_date == q_start, (
            f"Первая часть анализа старшей задачи должна начаться {q_start}, "
            f"а стоит {parts[0].start_date} — ушла за младшую задачу"
        )
        # Вторая часть — сразу за первой, а не за младшей задачей: у того же
        # человека она продолжает первую с остатка её последнего дня.
        expected = parts[0].end_date
        assert parts[1].start_date == expected, (
            f"Вторая часть должна начаться {expected}, а стоит "
            f"{parts[1].start_date}"
        )
        assert parts[1].end_date < low_an[0].end_date


def test_cascade_split_builds_parallel_branches(db_session):
    top = BacklogItem(
        title="top", priority=9,
        estimate_analyst_hours=40.0, estimate_dev_hours=40.0,
        estimate_qa_hours=16.0, estimate_opo_hours=8.0, opo_analyst_ratio=1.0,
    )
    # Младшая задача без анализа: разработчик у неё свободен с начала
    # квартала и занял бы дни, в которые первая часть разработки старшей
    # задачи должна идти параллельно второй части анализа.
    low = BacklogItem(title="low", priority=3, estimate_dev_hours=120.0)
    plan = _plan(db_session, "T_SPLIT_BRANCHES", [top, low])

    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(plan.id)
    an = _rows(db_session, plan.id, top.id, "analyst")[0]
    svc.split_assignment(an.id, [20.0, 20.0], cascade=True)
    db_session.commit()

    svc.compute_schedule(plan.id)
    db_session.expire_all()

    an1, an2 = _rows(db_session, plan.id, top.id, "analyst")
    dev1, dev2 = _rows(db_session, plan.id, top.id, "dev")
    qa1, qa2 = _rows(db_session, plan.id, top.id, "qa")
    opo1, opo2 = _rows(db_session, plan.id, top.id, "opo")
    name = {
        an1.id: "анализ 1", an2.id: "анализ 2",
        dev1.id: "разработка 1", dev2.id: "разработка 2",
        qa1.id: "тестирование 1", qa2.id: "тестирование 2",
        opo1.id: "ОПЭ 1",
    }

    def preds(row) -> set:
        return {
            name.get(pid, pid)
            for pid in db_session.execute(
                select(PhasePredecessor.predecessor_assignment_id).where(
                    PhasePredecessor.successor_assignment_id == row.id
                )
            ).scalars()
        }

    assert preds(an2) == {"анализ 1"}
    assert preds(dev1) == {"анализ 1"}
    assert preds(dev2) == {"анализ 2", "разработка 1"}
    assert preds(qa1) == {"разработка 1"}
    assert preds(qa2) == {"разработка 2", "тестирование 1"}
    # ОПЭ — эксплуатация задачи целиком: ждёт последнюю часть тестирования.
    assert preds(opo1) == {"тестирование 2"}
    assert preds(opo2) == {"тестирование 2", "ОПЭ 1"}

    # Ветка идёт параллельно: первая часть разработки — сразу за первой
    # частью анализа, не дожидаясь второй и не уступая дни младшей задаче.
    assert dev1.start_date == _next_working_day(an1.end_date)
    assert dev1.start_date <= an2.end_date
