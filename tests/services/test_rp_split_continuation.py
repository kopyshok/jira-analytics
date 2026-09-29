"""Части раздробленной фазы у одного человека идут подряд без дыр.

Реальный случай (аналитик с вовлечённостью 70% → 5,6 ч/день): часть 1
анализа OS-91437 кончалась днём с 2,8 ч, часть 2 начиналась лишь назавтра.
Остаток дня забирал анализ младшей задачи OS-90508 — и потом ещё на стыках
следующих частей: младшая задача начиналась раньше и визуально шла
параллельно раздробленной фазе.

Правило: следующая часть той же фазы той же задачи у того же человека —
продолжение, она берёт остаток дня, в который кончилась предыдущая часть.
Для других связей (другой человек, другая фаза) — по-прежнему со следующего
дня.
"""

import json
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models import PlanConflict, ResourcePlanAssignment
from app.services.resource_planning_service import (
    ResourcePlanningService,
    _earliest_after,
)
from tests.services.xteam_factory import add_item, make_employee, make_plan

# 8 ч × 70%.
DAY_CAP = 5.6


def _next_working_day(d: date) -> date:
    nxt = d + timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    return nxt


def _rows(db, plan_id: str, item_id: str, phase: str):
    return (
        db.execute(
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


def _daily(a: ResourcePlanAssignment) -> dict:
    return {
        date.fromisoformat(k): float(v)
        for k, v in json.loads(a.daily_hours_json or "{}").items()
    }


def _setup(db, team: str, analysts: int = 1, with_low: bool = True):
    emps = [
        make_employee(db, f"an{i}-{team}", team, role="analyst")
        for i in range(analysts)
    ]
    sc, plan = make_plan(db, team, quarter="Q4", year=2026)
    top = add_item(db, sc, "top", analyst=26.0, priority=9)
    top.involvement_analyst = 0.7
    low = None
    if with_low:
        low = add_item(db, sc, "low", analyst=20.0, priority=3)
        low.involvement_analyst = 0.7
    db.commit()
    return emps, plan, top, low


def _split(db, svc, plan_id: str, item_id: str, parts, cascade=False):
    svc.compute_schedule(plan_id)
    an = _rows(db, plan_id, item_id, "analyst")
    assert len(an) == 1
    svc.split_assignment(an[0].id, parts, cascade=cascade)
    db.commit()


def test_same_employee_parts_continue_on_leftover_of_the_day(db_session):
    db = db_session
    (analyst,), plan, top, low = _setup(db, "T_SPLIT_CONT")
    svc = ResourcePlanningService(db)
    _split(db, svc, plan.id, top.id, [14.0, 8.0, 4.0])

    # Два пересчёта подряд: второй раскладывает уже от дат первого.
    for _ in range(2):
        svc.compute_schedule(plan.id)
        db.expire_all()

        parts = _rows(db, plan.id, top.id, "analyst")
        assert [p.part_number for p in parts] == [1, 2, 3]
        assert all(p.employee_id == analyst.id for p in parts)

        # Каждая следующая часть начинается в день конца предыдущей и
        # добирает ровно остаток этого дня до потолка вовлечённости.
        for prev, nxt in zip(parts, parts[1:]):
            assert nxt.start_date == prev.end_date, (
                f"часть {nxt.part_number} начинается {nxt.start_date}, "
                f"а часть {prev.part_number} кончилась {prev.end_date}"
            )
            shared = prev.end_date
            assert _daily(prev)[shared] < DAY_CAP - 0.01
            assert abs(
                _daily(prev)[shared] + _daily(nxt)[shared] - DAY_CAP
            ) <= 0.01
        for p in parts:
            assert abs(sum(_daily(p).values()) - p.hours_allocated) <= 0.01

        # Младшая задача не влезает внутрь раздробленной фазы: ни часа
        # раньше дня, когда кончается её последняя часть.
        last_end = parts[-1].end_date
        low_rows = _rows(db, plan.id, low.id, "analyst")
        assert low_rows
        low_days = [d for r in low_rows for d in _daily(r)]
        assert min(low_days) >= last_end, (
            f"младшая задача взяла часы {min(low_days)} — раньше конца "
            f"раздробленной фазы {last_end}"
        )
        # Остаток последнего дня последней части младшая задача забрать может.
        assert min(low_days) == last_end

        # Потолок дня соблюдён на всех днях, включая общие.
        per_day: dict = {}
        for r in list(parts) + list(low_rows):
            for d, h in _daily(r).items():
                per_day[d] = per_day.get(d, 0.0) + h
        assert max(per_day.values()) <= DAY_CAP + 0.01

        violated = db.execute(
            select(PlanConflict).where(
                PlanConflict.plan_id == plan.id,
                PlanConflict.type == "PREDECESSOR_VIOLATED",
            )
        ).scalars().all()
        assert violated == []


def test_parts_of_different_employees_keep_next_day(db_session):
    db = db_session
    (an_a, an_b), plan, top, _ = _setup(
        db, "T_SPLIT_CONT_2EMP", analysts=2, with_low=False
    )
    svc = ResourcePlanningService(db)
    _split(db, svc, plan.id, top.id, [14.0, 12.0])

    p1, p2 = _rows(db, plan.id, top.id, "analyst")
    p2.employee_id = an_b.id if p1.employee_id == an_a.id else an_a.id
    db.commit()

    svc.compute_schedule(plan.id)
    db.expire_all()

    p1, p2 = _rows(db, plan.id, top.id, "analyst")
    assert p1.employee_id != p2.employee_id
    # Часть 1 кончается днём с остатком, но часть 2 у другого человека —
    # не продолжение: начинается со следующего рабочего дня.
    assert _daily(p1)[p1.end_date] < DAY_CAP - 0.01
    assert p2.start_date == _next_working_day(p1.end_date)


def test_cross_phase_edge_keeps_next_day(db_session):
    db = db_session
    (analyst,), plan, top, _ = _setup(db, "T_SPLIT_CONT_XPHASE", with_low=False)
    top.estimate_dev_hours = 16.0
    db.commit()
    svc = ResourcePlanningService(db)
    svc.compute_schedule(plan.id)
    # Разработку ведёт тот же человек, что и анализ.
    dev = _rows(db, plan.id, top.id, "dev")
    assert len(dev) == 1
    dev[0].employee_id = analyst.id
    dev[0].pinned_employee = True
    db.commit()
    an = _rows(db, plan.id, top.id, "analyst")
    svc.split_assignment(an[0].id, [14.0, 12.0], cascade=False)
    db.commit()

    svc.compute_schedule(plan.id)
    db.expire_all()

    an1, an2 = _rows(db, plan.id, top.id, "analyst")
    (dev,) = _rows(db, plan.id, top.id, "dev")
    assert dev.employee_id == analyst.id == an2.employee_id
    # Последняя часть анализа кончается днём с остатком, но разработка —
    # другая фаза: начинается со следующего рабочего дня.
    assert _daily(an2)[an2.end_date] < DAY_CAP - 0.01
    assert dev.start_date == _next_working_day(an2.end_date)


@pytest.mark.parametrize(
    "succ_kw, same_day",
    [
        ({}, True),
        ({"employee_id": "emp-2"}, False),
        ({"phase": "dev"}, False),
        ({"backlog_item_id": "item-2"}, False),
        ({"part_number": 1}, False),
    ],
    ids=["continuation", "other-employee", "other-phase", "other-item", "same-part"],
)
def test_earliest_after_rule(succ_kw, same_day):
    end = date(2026, 10, 5)
    pred = ResourcePlanAssignment(
        backlog_item_id="item-1", phase="analyst", employee_id="emp-1",
        part_number=1, end_date=end,
    )
    succ_fields = {
        "backlog_item_id": "item-1", "phase": "analyst",
        "employee_id": "emp-1", "part_number": 2,
    }
    succ_fields.update(succ_kw)
    succ = ResourcePlanAssignment(**succ_fields)
    expected = end if same_day else end + timedelta(days=1)
    assert _earliest_after(pred, succ) == expected


def test_earliest_after_qa_parts_keep_next_day():
    end = date(2026, 10, 5)
    pred = ResourcePlanAssignment(
        backlog_item_id="item-1", phase="qa", employee_id=None,
        part_number=1, end_date=end,
    )
    succ = ResourcePlanAssignment(
        backlog_item_id="item-1", phase="qa", employee_id=None, part_number=2,
    )
    assert _earliest_after(pred, succ) == end + timedelta(days=1)
