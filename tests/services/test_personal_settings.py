"""Чтение личных настроек сотрудника: действующая запись на квартал."""

from sqlalchemy import event

from app.models import EmployeePersonalNormed, EmployeePersonalSetting, MandatoryWorkType
from app.services.personal_settings import PersonalSetting, personal_for
from tests.services.xteam_factory import make_employee


def _setting(db, emp, year, quarter, involvement=None, normed=None):
    """Запись сотрудника; ``normed=None`` — по правилам роли, dict — свои проценты."""
    s = EmployeePersonalSetting(
        employee_id=emp.id, effective_year=year, effective_quarter=quarter,
        involvement=involvement, normed_custom=normed is not None,
    )
    for wt_id, pct in (normed or {}).items():
        s.normed.append(EmployeePersonalNormed(work_type_id=wt_id, percent_of_norm=pct))
    db.add(s)
    db.flush()
    return s


def _wt(db, code="support_consult"):
    w = MandatoryWorkType(code=code, label=code, subtracts_from_pool=True)
    db.add(w)
    db.flush()
    return w


def test_latest_record_not_after_quarter(db_session):
    p = make_employee(db_session, "Пряничников", "ERP", role="dev")
    _setting(db_session, p, 2026, 1, involvement=0.5)
    _setting(db_session, p, 2026, 3, involvement=1.0)
    _setting(db_session, p, 2027, 1, involvement=0.2)
    db_session.commit()

    assert personal_for(db_session, [p.id], 2025, 4) == {}
    assert personal_for(db_session, [p.id], 2026, 2)[p.id].involvement == 0.5
    assert personal_for(db_session, [p.id], 2026, 3)[p.id].involvement == 1.0
    assert personal_for(db_session, [p.id], 2026, 4)[p.id].involvement == 1.0
    assert personal_for(db_session, [p.id], 2027, 2)[p.id].involvement == 0.2


def test_later_back_to_general_record_overrides_earlier(db_session):
    wt = _wt(db_session)
    p = make_employee(db_session, "Пряничников", "ERP", role="dev")
    _setting(db_session, p, 2026, 1, involvement=1.0, normed={wt.id: 0})
    _setting(db_session, p, 2026, 3)
    db_session.commit()

    assert personal_for(db_session, [p.id], 2026, 2)[p.id] == PersonalSetting(1.0, {wt.id: 0.0})
    assert personal_for(db_session, [p.id], 2026, 4)[p.id] == PersonalSetting(None, None)


def test_custom_normed_empty_and_filled(db_session):
    wt = _wt(db_session)
    org = _wt(db_session, "organizational")
    p = make_employee(db_session, "Пряничников", "ERP", role="dev")
    s = make_employee(db_session, "Шутов", "ERP", role="dev")
    nobody = make_employee(db_session, "Иванов", "ERP", role="dev")
    _setting(db_session, p, 2026, 4, normed={})
    _setting(db_session, s, 2026, 4, involvement=0.9, normed={wt.id: 5, org.id: 10})
    db_session.commit()

    got = personal_for(db_session, [p.id, s.id, nobody.id], 2026, 4)

    assert got[p.id] == PersonalSetting(None, {})
    assert got[s.id] == PersonalSetting(0.9, {wt.id: 5.0, org.id: 10.0})
    assert nobody.id not in got


def test_query_count_is_constant(db_session):
    wt = _wt(db_session)
    ids = []
    for i in range(10):
        e = make_employee(db_session, f"Сотрудник {i}", "ERP", role="dev")
        _setting(db_session, e, 2026, 1, involvement=0.5)
        _setting(db_session, e, 2026, 3, involvement=1.0, normed={wt.id: i})
        ids.append(e.id)
    db_session.commit()

    engine = db_session.get_bind()
    counter = {"n": 0}

    def _hook(*_args):
        counter["n"] += 1

    event.listen(engine, "before_cursor_execute", _hook)
    try:
        got = personal_for(db_session, ids, 2026, 4)
    finally:
        event.remove(engine, "before_cursor_execute", _hook)

    assert len(got) == 10
    assert counter["n"] <= 3


def test_no_employees_no_queries(db_session):
    assert personal_for(db_session, [], 2026, 4) == {}
