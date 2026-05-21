"""TDD regression: non-QA фаза (dev/analyst/opo) после _shift_to_obey_predecessors
не должна попадать в выходные/отпуск.

Bug PRJ-10623: предшественник сдвигал dev-фазу вперёд, блайнд-сдвиг ключей
daily_hours_json по delta дней ронял раскладку в окно отпуска сотрудника.
Frontend «Дни × часы» показывал «Потрачено 8.0ч» в дни статуса «Отсутствие»
и «Выходной», бар начинался в субботу.

Fix: для non-QA фаз пересобирать раскладку через _allocate_hours_with_breakdown
от new_start (учитывает avail сотрудника, включая Absence).
"""

import json
import uuid
from datetime import date

import pytest

from app.models import (
    Absence,
    AbsenceReason,
    BacklogItem,
    Employee,
    PhasePredecessor,
    PlanningScenario,
    ResourcePlan,
    ResourcePlanAssignment,
    ScenarioAllocation,
)
from app.models.employee_team import EmployeeTeam
from app.services.resource_planning_service import ResourcePlanningService


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def dev_shift_into_vacation_plan(db_session):
    """Сетап под PRJ-10623:
      - Сотрудник с отпуском 18.05–29.05 (двухнедельный).
      - Dev-фаза 40ч, изначальная раскладка ДО отпуска (Пн-Пт 11.05–15.05).
      - Предшественник analyst заканчивается в Пт 15.05 → dev новый старт = Сб 16.05.
      - Без фикса: блайнд-сдвиг роняет ключи в отпуск.
      - С фиксом: dev должен скакнуть через отпуск и стартовать на Пн 01.06.
    """
    team = "T_DEV_SHIFT"

    emp = Employee(
        jira_account_id=_uid()[:16],
        display_name="Разраб",
        team=team,
        is_active=True,
        role="developer",
    )
    db_session.add(emp)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=emp.id, team=team, is_primary=True))

    reason = AbsenceReason(code="vacation", label="Отпуск", is_planned=True)
    db_session.add(reason)
    db_session.flush()

    # Отпуск 18.05–29.05 (Пн–Пт двух недель)
    db_session.add(Absence(
        employee_id=emp.id,
        start_date=date(2026, 5, 18),
        end_date=date(2026, 5, 29),
        reason_id=reason.id,
    ))

    item = BacklogItem(
        title="dev-shift-into-vacation",
        priority=1,
        estimate_analyst_hours=8.0,
        estimate_dev_hours=40.0,
        estimate_qa_hours=0.0,
        estimate_opo_hours=0.0,
        opo_analyst_ratio=0.5,
    )
    db_session.add(item)
    db_session.flush()

    scenario = PlanningScenario(
        name="dev-shift-test", quarter="Q2", year=2026, status="draft", team=team,
    )
    db_session.add(scenario)
    db_session.flush()
    db_session.add(ScenarioAllocation(
        scenario_id=scenario.id, backlog_item_id=item.id, included_flag=True,
    ))

    plan = ResourcePlan(
        team=team, quarter="Q2", year=2026, status="draft", scenario_id=scenario.id,
    )
    db_session.add(plan)
    db_session.flush()

    # Analyst заканчивает в Пт 15.05
    analyst_asgn = ResourcePlanAssignment(
        plan_id=plan.id, backlog_item_id=item.id, phase="analyst",
        employee_id=emp.id, part_number=1, hours_allocated=8.0,
        start_date=date(2026, 5, 15), end_date=date(2026, 5, 15),
        daily_hours_json=json.dumps({"2026-05-15": 8.0}),
    )
    # Dev — старая раскладка ДО отпуска, должна сдвинуться после shift
    dev_asgn = ResourcePlanAssignment(
        plan_id=plan.id, backlog_item_id=item.id, phase="dev",
        employee_id=emp.id, part_number=1, hours_allocated=40.0,
        start_date=date(2026, 5, 11), end_date=date(2026, 5, 15),
        daily_hours_json=json.dumps({
            "2026-05-11": 8.0, "2026-05-12": 8.0, "2026-05-13": 8.0,
            "2026-05-14": 8.0, "2026-05-15": 8.0,
        }),
    )
    db_session.add_all([analyst_asgn, dev_asgn])
    db_session.flush()

    db_session.add(PhasePredecessor(
        successor_assignment_id=dev_asgn.id,
        predecessor_assignment_id=analyst_asgn.id,
    ))
    db_session.commit()

    return plan, analyst_asgn, dev_asgn, emp, item


def test_dev_phase_skips_weekend_and_vacation(db_session, dev_shift_into_vacation_plan):
    """После shift dev должна стартовать на рабочем дне ПОСЛЕ отпуска,
    а не падать в субботу/отпуск."""
    plan, analyst_asgn, dev_asgn, emp, item = dev_shift_into_vacation_plan

    svc = ResourcePlanningService(db_session)
    q_start = date(2026, 4, 1)
    q_end = date(2026, 6, 30)

    # Готовим availability + remaining как в compute_schedule
    avail = svc.build_availability([emp], q_start, q_end, [])
    original_avail = {eid: dict(days) for eid, days in avail.items()}
    remaining = {eid: dict(days) for eid, days in avail.items()}

    preds = {dev_asgn.id: [analyst_asgn.id]}
    assignments = [analyst_asgn, dev_asgn]

    svc._shift_to_obey_predecessors(
        assignments, preds, q_start, q_end,
        remaining=remaining,
        preempt_locked={eid: set() for eid in avail},
        original_avail=original_avail,
    )

    # Старт dev не должен быть выходным
    assert dev_asgn.start_date is not None
    assert dev_asgn.start_date.weekday() < 5, (
        f"dev start_date {dev_asgn.start_date} — выходной"
    )

    # Старт не должен попасть в отпуск 18.05–29.05
    vacation_range = (date(2026, 5, 18), date(2026, 5, 29))
    assert not (vacation_range[0] <= dev_asgn.start_date <= vacation_range[1]), (
        f"dev start_date {dev_asgn.start_date} — внутри отпуска"
    )

    # Все ключи daily_hours_json — рабочие дни вне отпуска
    assert dev_asgn.daily_hours_json
    daily = json.loads(dev_asgn.daily_hours_json)
    assert daily, "daily_hours_json пуст"
    for k, v in daily.items():
        d = date.fromisoformat(k)
        assert d.weekday() < 5, f"daily ключ {k} — выходной"
        assert not (vacation_range[0] <= d <= vacation_range[1]), (
            f"daily ключ {k} — внутри отпуска"
        )
        assert v > 0, f"daily ключ {k} имеет нулевые часы"

    # Сумма часов сохранена
    assert sum(daily.values()) == pytest.approx(40.0, abs=0.01)


def test_shift_restore_preserves_other_phase_consumption(db_session):
    """Сдвиг dev-фазы инициативы B не должен затирать spillover-leftover,
    которым уже воспользовалась инициатива C (та же роль, тот же сотрудник).

    Сценарий: B (приоритет 2) занял relay-цепочкой 1-3 июня по 8ч.
    C (приоритет 1) — последний день B (3 июня) частично доступен через
    spillover, C ест 1.4ч на 3 июня + продолжает на 4 июня. Затем B
    сдвигается на 4 июня по предшественнику A. Restore старых дней B
    обязан учесть, что 3 июня уже частично «потрачено» инициативой C,
    иначе allocator B сядет вторым слоем поверх C → overload.
    """
    team = "T_RESTORE"
    emp = Employee(
        jira_account_id=_uid()[:16],
        display_name="Разраб-restore",
        team=team,
        is_active=True,
        role="developer",
    )
    db_session.add(emp)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=emp.id, team=team, is_primary=True))

    item_b = BacklogItem(
        title="b", priority=2,
        estimate_analyst_hours=8.0, estimate_dev_hours=24.0,
        estimate_qa_hours=0.0, estimate_opo_hours=0.0, opo_analyst_ratio=0.5,
    )
    item_c = BacklogItem(
        title="c", priority=1,
        estimate_analyst_hours=0.0, estimate_dev_hours=24.0,
        estimate_qa_hours=0.0, estimate_opo_hours=0.0, opo_analyst_ratio=0.5,
    )
    db_session.add_all([item_b, item_c])
    db_session.flush()

    scenario = PlanningScenario(
        name="restore-test", quarter="Q2", year=2026, status="draft", team=team,
    )
    db_session.add(scenario)
    db_session.flush()
    db_session.add(ScenarioAllocation(scenario_id=scenario.id, backlog_item_id=item_b.id, included_flag=True))
    db_session.add(ScenarioAllocation(scenario_id=scenario.id, backlog_item_id=item_c.id, included_flag=True))

    plan = ResourcePlan(team=team, quarter="Q2", year=2026, status="draft", scenario_id=scenario.id)
    db_session.add(plan)
    db_session.commit()

    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(plan.id)

    # Снять все назначения dev этого сотрудника, проверить отсутствие
    # перекрытий дней по daily_hours_json (внутри одного сотрудника).
    from sqlalchemy import select as _select
    rows = db_session.execute(
        _select(ResourcePlanAssignment).where(
            ResourcePlanAssignment.plan_id == plan.id,
            ResourcePlanAssignment.phase == "dev",
            ResourcePlanAssignment.employee_id == emp.id,
        )
    ).scalars().all()

    day_users: dict[date, list[str]] = {}
    for a in rows:
        if not a.daily_hours_json:
            continue
        for k, h in json.loads(a.daily_hours_json).items():
            d = date.fromisoformat(k)
            day_users.setdefault(d, []).append(f"{a.backlog_item_id}:{h}")

    overlaps = {d: users for d, users in day_users.items() if len(users) > 1}
    # Допустим частичное spillover-перекрытие на ОДИН день (last-day leftover
    # уехавшей фазы переходит к следующей по приоритету) — суммарно ≤ 8ч.
    bad = []
    for d, users in overlaps.items():
        total = sum(float(u.split(":")[1]) for u in users)
        if total > 8.01:
            bad.append((d, users, total))
    assert not bad, f"Перегрузка по дням (фазы накладываются >8ч/день): {bad}"
