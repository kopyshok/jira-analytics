"""Фабрики для тестов запаса нормированных работ (сервис и диаграмма)."""

from __future__ import annotations

from datetime import date, timedelta

from app.models import MandatoryWorkType, ScenarioRule
from tests.services.xteam_factory import add_item, book, join_team, make_employee, make_plan

D = date.fromisoformat


def _types(db):
    """Виды работ: четыре уменьшают запас на проекты, «Прочие / Чужие» — нет."""
    out = {}
    for i, code in enumerate(["organizational", "support_consult", "minor_change", "technical_tasks"]):
        w = MandatoryWorkType(code=code, label=code, sort_order=i, subtracts_from_pool=True)
        db.add(w)
        out[code] = w
    db.add(MandatoryWorkType(code="other_foreign", label="Прочие", subtracts_from_pool=False))
    db.flush()
    return out


def _rules(db, scenario, types, role="dev"):
    """Правила роли: орг. вопросы 10, сопровождение 15, минорные 20, технические 10."""
    for code, pct in {"organizational": 10, "support_consult": 15, "minor_change": 20,
                      "technical_tasks": 10}.items():
        db.add(ScenarioRule(scenario_id=scenario.id, role=role, work_type_id=types[code].id,
                            percent_of_norm=pct))
    db.flush()


def _weekdays(start, n):
    """``n`` будней подряд с ``start`` (ISO-строки)."""
    out, d = [], D(start)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _erp(db):
    """ERP: два разработчика; P занят в опорном плане «Блока» 180 ч.

    I кв. 2026 без записей календаря: 64 будня × 8 ч = 512 ч нормы у каждого.
    Бронь P в «Блоке» — 25 будней с 12.01 по 7,2 ч = 180 ч. Опорный план ERP —
    ``ResourcePlan`` с ``team == "ERP"``.
    """
    types = _types(db)
    p = make_employee(db, "Пряничников", "ERP", role="dev")
    s = make_employee(db, "Шутов", "ERP", role="dev")
    join_team(db, p, "Блок")
    sc, _plan = make_plan(db, "ERP")
    _rules(db, sc, types)
    bsc, bplan = make_plan(db, "Блок")
    item = add_item(db, bsc, "OS-92122", dev=180)
    book(db, bplan, item, p, {d: 7.2 for d in _weekdays("2026-01-12", 25)})
    db.commit()
    return types, p, s, item
