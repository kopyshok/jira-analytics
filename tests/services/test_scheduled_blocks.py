"""Кого и в какие дни закрывает заблокированный период."""

from datetime import date

from app.models import MandatoryWorkType, Role, ScheduledBlock, ScheduledBlockEmployee, ScheduledBlockRole
from app.services.scheduled_blocks import resolve_blocked_days
from tests.services.xteam_factory import join_team, make_employee

D = date.fromisoformat


def _wt(db, code="support_consult"):
    w = MandatoryWorkType(code=code, label=code, subtracts_from_pool=True)
    db.add(w)
    db.flush()
    return w


def _role(db, code):
    r = Role(code=code, label=code)
    db.add(r)
    db.flush()
    return r


def _block(db, team, start, end, wt=None, roles=(), employees=(), reason="Закрытие месяца"):
    b = ScheduledBlock(team=team, start_date=D(start), end_date=D(end), reason=reason,
                       work_type_id=wt.id if wt else None)
    b.roles = [ScheduledBlockRole(role_id=r.id) for r in roles]
    b.employees = [ScheduledBlockEmployee(employee_id=e.id) for e in employees]
    db.add(b)
    db.flush()
    return b


def test_employee_block_overrides_role_block_within_month(db_session):
    wt = _wt(db_session)
    analyst = _role(db_session, "analyst")
    ivanov = make_employee(db_session, "Иванов", "ERP", role="analyst")
    petrov = make_employee(db_session, "Петров", "ERP", role="analyst")
    _block(db_session, "ERP", "2026-10-05", "2026-10-07", wt, roles=[analyst])
    _block(db_session, "ERP", "2026-11-05", "2026-11-06", wt, roles=[analyst])
    _block(db_session, "ERP", "2026-10-08", "2026-10-09", wt, employees=[ivanov])

    hits = resolve_blocked_days(db_session, [ivanov, petrov], D("2026-10-01"), D("2026-11-30"), "ERP")

    assert sorted(hits[ivanov.id]) == [D("2026-10-08"), D("2026-10-09"), D("2026-11-05"), D("2026-11-06")]
    assert sorted(hits[petrov.id]) == [D("2026-10-05"), D("2026-10-06"), D("2026-10-07"),
                                       D("2026-11-05"), D("2026-11-06")]
    assert hits[petrov.id][D("2026-10-05")].work_type_id == wt.id


def test_role_block_beats_team_block_but_other_types_stay(db_session):
    wt, other = _wt(db_session), _wt(db_session, "organizational")
    dev = _role(db_session, "dev")
    e = make_employee(db_session, "Шутов", "ERP", role="dev")
    _block(db_session, "ERP", "2026-12-07", "2026-12-08", wt)                # вся команда
    _block(db_session, "ERP", "2026-12-10", "2026-12-10", wt, roles=[dev])   # роль
    _block(db_session, "ERP", "2026-12-14", "2026-12-14", other)             # другой вид

    hits = resolve_blocked_days(db_session, [e], D("2026-12-01"), D("2026-12-31"), "ERP")

    assert sorted(hits[e.id]) == [D("2026-12-10"), D("2026-12-14")]


def test_primary_team_block_closes_day_in_other_team_plan(db_session):
    wt = _wt(db_session)
    e = make_employee(db_session, "Пряничников", "ERP", role="dev")
    join_team(db_session, e, "Блок")
    _block(db_session, "ERP", "2026-10-05", "2026-10-07", wt)
    _block(db_session, "Блок", "2026-10-12", "2026-10-12", wt)

    in_block_plan = resolve_blocked_days(db_session, [e], D("2026-10-01"), D("2026-10-31"), "Блок")
    in_erp_plan = resolve_blocked_days(db_session, [e], D("2026-10-01"), D("2026-10-31"), "ERP")

    # В плане «Блока»: периоды основной ERP и периоды самого «Блока» (он там состоит).
    assert sorted(in_block_plan[e.id]) == [D("2026-10-05"), D("2026-10-06"), D("2026-10-07"), D("2026-10-12")]
    # В плане ERP период неосновного «Блока» его не закрывает.
    assert sorted(in_erp_plan[e.id]) == [D("2026-10-05"), D("2026-10-06"), D("2026-10-07")]
    assert in_block_plan[e.id][D("2026-10-05")].team == "ERP"


def test_borrowed_not_closed_by_plan_team_blocks(db_session):
    e = make_employee(db_session, "Гость", "ERP", role="dev")
    _block(db_session, "Блок", "2026-10-05", "2026-10-05")

    assert resolve_blocked_days(db_session, [e], D("2026-10-01"), D("2026-10-31"), "Блок") == {}


def test_blocks_without_team_apply_to_everyone_and_untyped_group(db_session):
    e = make_employee(db_session, "Любой", "ERP", role="qa")
    _block(db_session, None, "2026-10-05", "2026-10-05", reason="Субботник")

    hits = resolve_blocked_days(db_session, [e], D("2026-10-01"), D("2026-10-31"), "ERP")

    assert hits[e.id][D("2026-10-05")].work_type_id is None
    assert hits[e.id][D("2026-10-05")].reason == "Субботник"


def test_cells_by_team_skips_own_and_global(db_session):
    from app.services.scheduled_blocks import cells_by_team

    wt = _wt(db_session)
    e = make_employee(db_session, "Пряничников", "ERP", role="dev")
    join_team(db_session, e, "Блок")
    _block(db_session, "ERP", "2026-10-05", "2026-10-05", wt)
    _block(db_session, "Блок", "2026-10-06", "2026-10-06", wt)
    _block(db_session, None, "2026-10-07", "2026-10-07")

    hits = resolve_blocked_days(db_session, [e], D("2026-10-01"), D("2026-10-31"), "Блок")

    assert cells_by_team(hits, exclude_team="Блок") == {"ERP": [(e.id, "2026-10-05")]}
