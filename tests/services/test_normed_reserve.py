"""Запас нормированных работ команды и раскладка по дням."""

from datetime import datetime, timedelta

from sqlalchemy import event, select

from app.models import (
    Absence,
    AbsenceReason,
    ResourcePlan,
    ScenarioRule,
    ScheduledBlock,
    TeamWorkTypeOverride,
)
from app.services import normed_reserve as nr
from app.services.scheduled_blocks import BlockHit
from tests.services.normed_factory import D, _erp, _personal, _rules, _types, _weekdays
from tests.services.xteam_factory import book, join_team, make_employee, make_plan

Q = (2026, 1)  # 2026-01-01 … 2026-03-31; календарь без аномалий — 8 ч в будни


def test_team_reserve_shared_tech_pool_is_eaten_by_one_person(db_session):
    types, p, s, _item = _erp(db_session)

    r = nr.team_reserve(db_session, "ERP", *Q)

    norm = r.people[p.id].norm
    assert norm == r.people[s.id].norm == 64 * 8.0
    tech = next(x for x in r.roles["dev"] if x.work_type_id == types["technical_tasks"].id)
    assert round(tech.planned, 1) == round(0.10 * 2 * norm, 1)
    assert round(tech.other_teams, 1) == 180.0
    assert tech.remaining == 0.0
    assert round(tech.overuse, 1) == round(180.0 - tech.planned, 1)
    assert types["technical_tasks"].id not in r.people[s.id].share
    assert round(r.people[s.id].undated, 1) == round(0.45 * norm, 1)
    assert [round(w.hours, 1) for w in r.other_team_work] == [180.0]  # 25 × 7,2 в float — 179,99…
    assert r.other_team_work[0].work_type_id == types["technical_tasks"].id
    assert r.other_team_work[0].is_manual is False


def test_override_moves_other_team_work_to_chosen_type(db_session):
    types, p, s, item = _erp(db_session)
    db_session.add(TeamWorkTypeOverride(team="ERP", backlog_item_id=item.id,
                                        work_type_id=types["support_consult"].id))
    db_session.commit()

    r = nr.team_reserve(db_session, "ERP", *Q)

    rows = {x.work_type_id: x for x in r.roles["dev"]}
    assert rows[types["technical_tasks"].id].other_teams == 0.0
    assert round(rows[types["support_consult"].id].other_teams, 1) == 180.0
    assert r.other_team_work[0].is_manual is True


def test_home_block_consumes_its_type_for_the_person(db_session):
    types, p, s, _item = _erp(db_session)
    db_session.add(ScheduledBlock(team="ERP", start_date=D("2026-01-05"), end_date=D("2026-01-07"),
                                  reason="Закрытие месяца", work_type_id=types["support_consult"].id))
    db_session.commit()

    r = nr.team_reserve(db_session, "ERP", *Q)

    support = next(x for x in r.roles["dev"] if x.work_type_id == types["support_consult"].id)
    assert support.blocked == 2 * 3 * 8.0  # оба разработчика, три дня
    assert r.people[p.id].blocked[types["support_consult"].id] == 24.0


def test_erp_example_person_quarter_over_norm(db_session):
    """Пример спеки 5.10: задачи ERP 176 + «Блок» 180 + нормированные 230,4 ч."""
    _types_, p, _s, _item = _erp(db_session)
    r = nr.team_reserve(db_session, "ERP", *Q)
    cap = nr.calendar_hours(db_session, D("2026-01-01"), D("2026-03-31"))
    ext_days = [D(x) for x in _weekdays("2026-01-12", 25)]
    other = {d: 7.2 for d in ext_days}
    residue = {d: 0.1 for d in ext_days}  # вовлечённость «Блока» 90%
    own = {d: 8.0 for d in [d for d in sorted(cap) if d not in other][:22]}

    load = nr.place_person(cap, own, other, residue, {}, r.people[p.id], r.labels)

    assert round(load.normed, 1) == 230.4
    # 20 ч — остатки дней «Блока», 17 свободных дней × 8 = 136 ч, 74,4 ч не вмещается.
    assert round(load.unplaced, 1) == 74.4
    assert round(load.pct) == 115


def test_norm_counts_only_primary_days_without_absences(db_session):
    types = _types(db_session)
    x = make_employee(db_session, "Переходящий", "ERP", role="dev", member=False)
    join_team(db_session, x, "ERP", left_at=D("2026-02-01"), primary=True)
    join_team(db_session, x, "Другая", joined_at=D("2026-02-01"), primary=True)
    y = make_employee(db_session, "Постоянный", "ERP", role="dev")
    reason = AbsenceReason(code="vacation", label="Отпуск", is_planned=True)
    db_session.add(reason)
    db_session.flush()
    db_session.add(Absence(employee_id=x.id, start_date=D("2026-01-12"), end_date=D("2026-01-16"),
                           reason_id=reason.id))
    sc, _plan = make_plan(db_session, "ERP")
    _rules(db_session, sc, types)
    db_session.commit()

    r = nr.team_reserve(db_session, "ERP", *Q)

    assert r.people[x.id].norm == (22 - 5) * 8.0  # январь без недели отпуска
    assert r.people[y.id].norm == 64 * 8.0
    org = types["organizational"].id
    assert round(r.people[x.id].share[org], 2) == round(0.10 * (136 + 512) * 136 / (136 + 512), 2)


def _count_queries(db, fn) -> int:
    """SQL-запросы, сделанные внутри fn() через сессию db."""
    engine = db.get_bind()
    counter = {"n": 0}

    def _hook(conn, cursor, statement, parameters, context, executemany):
        counter["n"] += 1

    event.listen(engine, "before_cursor_execute", _hook)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", _hook)
    return counter["n"]


def test_query_count_does_not_grow_with_team_size(db_session):
    types, _p, _s, item = _erp(db_session)
    db_session.add(ScheduledBlock(team="ERP", start_date=D("2026-01-05"), end_date=D("2026-01-07"),
                                  reason="Закрытие месяца", work_type_id=types["support_consult"].id))
    db_session.commit()
    small = _count_queries(db_session, lambda: nr.team_reserve(db_session, "ERP", *Q))

    bplan = db_session.execute(select(ResourcePlan).where(ResourcePlan.team == "Блок")).scalar_one()
    for i in range(5):
        e = make_employee(db_session, f"Ещё {i}", "ERP", role="dev")
        join_team(db_session, e, "Блок")
        book(db_session, bplan, item, e, {d: 4.0 for d in _weekdays("2026-02-02", 5)})
    db_session.commit()
    big = _count_queries(db_session, lambda: nr.team_reserve(db_session, "ERP", *Q))

    assert big == small


def test_reference_scenario_approved_then_freshest_draft(db_session):
    approved, _ = make_plan(db_session, "ERP", scenario_updated_at=datetime(2026, 1, 1))
    make_plan(db_session, "ERP", scenario_status="draft", scenario_updated_at=datetime(2026, 2, 1))
    make_plan(db_session, "Блок", scenario_status="draft", scenario_updated_at=datetime(2026, 1, 1))
    fresh, _ = make_plan(db_session, "Блок", scenario_status="draft", scenario_updated_at=datetime(2026, 2, 1))
    make_plan(db_session, "Блок", scenario_status="draft", scenario_updated_at=datetime(2026, 1, 15))
    db_session.commit()

    assert nr.reference_scenario(db_session, "ERP", *Q).id == approved.id
    assert nr.reference_scenario(db_session, "Блок", *Q).id == fresh.id


def test_employee_without_role_uses_all_roles_rules(db_session):
    types = _types(db_session)
    e = make_employee(db_session, "Без роли", "ERP", role=None)
    sc, _plan = make_plan(db_session, "ERP")
    _rules(db_session, sc, types, role="dev")
    org = types["organizational"].id
    db_session.add(ScenarioRule(scenario_id=sc.id, role=None, work_type_id=org, percent_of_norm=5))
    db_session.commit()

    r = nr.team_reserve(db_session, "ERP", *Q)

    assert {wt: round(h, 2) for wt, h in r.people[e.id].share.items()} == {org: round(0.05 * 512, 2)}


def test_role_with_zero_rules_does_not_fall_back_to_all_roles(db_session):
    types = _types(db_session)
    qa = make_employee(db_session, "Тестировщик", "ERP", role="qa")
    dev = make_employee(db_session, "Разработчик", "ERP", role="dev")
    sc, _plan = make_plan(db_session, "ERP")
    tech = types["technical_tasks"].id
    db_session.add(ScenarioRule(scenario_id=sc.id, role=None, work_type_id=tech, percent_of_norm=10))
    for w in types.values():
        db_session.add(ScenarioRule(scenario_id=sc.id, role="qa", work_type_id=w.id, percent_of_norm=0))
    db_session.commit()

    r = nr.team_reserve(db_session, "ERP", *Q)

    assert r.people[qa.id].undated == 0.0
    assert sum(x.planned for x in r.roles.get("qa", [])) == 0.0
    assert round(r.people[dev.id].share[tech], 2) == round(0.10 * 512, 2)


def test_text_quarter_works_like_number(db_session):
    _types_, p, _s, _item = _erp(db_session)

    by_num = nr.team_reserve(db_session, "ERP", 2026, 1)

    for q in ("Q1", "1"):
        by_text = nr.team_reserve(db_session, "ERP", 2026, q)
        assert by_text.scenario_id == by_num.scenario_id
        assert by_text.people[p.id].norm == by_num.people[p.id].norm
        assert by_text.people[p.id].share == by_num.people[p.id].share
        assert [w.hours for w in by_text.other_team_work] == [w.hours for w in by_num.other_team_work]
    assert nr.team_reserve(db_session, "ERP", 2026, "Q9") is None


def test_other_team_and_teamless_blocks_do_not_consume_reserve(db_session):
    types, p, s, _item = _erp(db_session)  # P ещё и в «Блоке» (не основная)
    support = types["support_consult"].id
    db_session.add(ScheduledBlock(team="Блок", start_date=D("2026-01-05"), end_date=D("2026-01-07"),
                                  reason="Закрытие месяца", work_type_id=support))
    db_session.add(ScheduledBlock(team=None, start_date=D("2026-01-12"), end_date=D("2026-01-12"),
                                  reason="Субботник", work_type_id=support))
    db_session.commit()

    r = nr.team_reserve(db_session, "ERP", *Q)

    row = next(x for x in r.roles["dev"] if x.work_type_id == support)
    assert row.blocked == 0.0
    assert r.people[p.id].blocked == {} and r.people[s.id].blocked == {}


def test_team_without_rules_has_no_reserve(db_session):
    make_employee(db_session, "Один", "Пусто", role="dev")
    make_plan(db_session, "Пусто")
    db_session.commit()

    assert nr.team_reserve(db_session, "Пусто", *Q) is None


def test_place_person_residue_then_free_days_then_unplaced():
    days = [D("2026-01-05") + timedelta(days=i) for i in range(5)]  # Пн–Пт
    capacity = {d: 8.0 for d in days}
    own = {days[0]: 7.2, days[1]: 7.2}
    residue = {days[0]: 0.1, days[1]: 0.1}
    reserve = nr.PersonReserve("e", "dev", 40.0, share={"wt": 20.0})
    blocked = {days[4]: BlockHit("b", "ERP", "wt2", "Закрытие месяца")}

    load = nr.place_person(capacity, own, {}, residue, blocked, reserve, {"wt": "Минорные", "wt2": "Сопровождение"})

    # 8 − 7,2 в двоичной арифметике — 0,7999…8: сравнение с округлением.
    assert round(load.normed_by_day[days[0]], 2) == 0.8 and round(load.normed_by_day[days[1]], 2) == 0.8
    assert load.normed_by_day[days[4]] == 8.0
    # Доля 20 ч: 1,6 ч — остатки Пн/Вт; 18,4 ч — на свободные Ср/Чт (16 ч), 2,4 ч не поместились.
    assert round(load.normed_by_day[days[2]], 2) == 8.0 and round(load.normed_by_day[days[3]], 2) == 8.0
    assert round(load.unplaced, 2) == 2.4
    assert round(load.normed, 2) == 28.0          # 8 заблокировано + 20 доля
    assert round(load.pct, 1) == round((14.4 + 28.0) / 40 * 100, 1)
    assert load.normed_by_type == {"Сопровождение": 8.0, "Минорные": 20.0}


def test_place_person_fills_days_without_tasks_first():
    """Остаток доли — сначала поровну на дни без задач (сокращённый день берёт
    меньше пропорционально своим часам); остаток свободного времени дней с
    задачами (своих или других команд) — только если дней без задач не хватило."""
    mon, tue, wed, thu, fri = [D("2026-01-05") + timedelta(days=i) for i in range(5)]
    capacity = {mon: 8.0, tue: 8.0, wed: 8.0, thu: 8.0, fri: 4.0}  # пятница — сокращённый день
    own = {mon: 4.0}
    other = {tue: 2.0}
    residue = {mon: 0.1, tue: 0.1}  # вовлечённость 90%: 0,8 ч остатка дня

    def place(share):
        reserve = nr.PersonReserve("e", "dev", 36.0, share={"wt": share})
        return nr.place_person(capacity, own, other, residue, {}, reserve, {"wt": "Минорные"})

    # 10 ч: 1,6 ч — остатки Пн/Вт; 8,4 ч — на Ср/Чт/Пт (20 ч) пропорционально часам.
    load = place(10.0)
    by_day = {d: round(h, 2) for d, h in load.normed_by_day.items()}
    assert (by_day[mon], by_day[tue]) == (0.8, 0.8)
    assert (by_day[wed], by_day[thu], by_day[fri]) == (3.36, 3.36, 1.68)
    assert load.unplaced == 0.0

    # 25,8 ч: дни без задач заняты целиком (20 ч), 4,2 ч — на свободное время
    # дней с задачами (Пн 3,2 ч, Вт 5,2 ч) пропорционально, по половине.
    load = place(25.8)
    by_day = {d: round(h, 2) for d, h in load.normed_by_day.items()}
    assert (by_day[wed], by_day[thu], by_day[fri]) == (8.0, 8.0, 4.0)
    assert (by_day[mon], by_day[tue]) == (2.4, 3.4)
    assert round(load.unplaced, 2) == 0.0

    # 40 ч: всё свободное занято, 10 ч не вмещается.
    load = place(40.0)
    by_day = {d: round(h, 2) for d, h in load.normed_by_day.items()}
    assert (by_day[mon], by_day[tue]) == (4.0, 6.0)
    assert round(load.unplaced, 2) == 10.0


def test_place_person_no_free_days_spreads_share_over_residue_then_leftovers():
    """Каждый день занят задачей (своей или чужой команды) — дней без задач нет.
    Доля запаса сначала добирает остаток дня после вовлечённости на каждом
    дне, затем — оставшееся свободное время дней с задачами пропорционально;
    что не поместилось — unplaced."""
    mon, tue, wed = [D("2026-01-05") + timedelta(days=i) for i in range(3)]
    capacity = {mon: 8.0, tue: 8.0, wed: 8.0}
    own = {mon: 5.0, tue: 6.0}
    other = {wed: 7.0}
    residue = {mon: 0.1, tue: 0.1, wed: 0.1}  # вовлечённость 90% на всех днях
    reserve = nr.PersonReserve("e", "dev", 24.0, share={"wt": 8.0})

    load = nr.place_person(capacity, own, other, residue, {}, reserve, {"wt": "Минорные"})

    # Остаток вовлечённости — 0,8 ч (10% от 8 ч) на каждый день, свободного хватает.
    # Свободное время после остатка: Пн 2,2 ч, Вт 1,2 ч, Ср 0,2 ч (итого 3,6 ч).
    # Из оставшихся 5,6 ч доли на них уходит всё свободное (3,6 ч), 2,0 ч не поместились.
    by_day = {d: round(h, 2) for d, h in load.normed_by_day.items()}
    assert by_day == {mon: 3.0, tue: 2.0, wed: 1.0}
    assert round(load.unplaced, 2) == 2.0
    assert round(load.normed, 2) == 8.0  # блока нет, вся доля запаса — 8 ч
    assert round(load.pct, 1) == round((11.0 + 7.0 + 8.0) / 24.0 * 100, 1)


def test_place_person_all_days_blocked_share_is_fully_unplaced():
    """Все дни квартала заблокированы: норма дня целиком уходит в блок, для
    доли запаса свободного времени не остаётся — вся доля не помещается."""
    mon, tue = [D("2026-01-05") + timedelta(days=i) for i in range(2)]
    capacity = {mon: 8.0, tue: 8.0}
    reserve = nr.PersonReserve("e", "dev", 16.0, share={"wt1": 10.0})
    blocked = {
        mon: BlockHit("b", "ERP", "wt2", "Закрытие месяца"),
        tue: BlockHit("b", "ERP", "wt2", "Закрытие месяца"),
    }

    load = nr.place_person(
        capacity, {}, {}, {}, blocked, reserve, {"wt1": "Минорные", "wt2": "Сопровождение"}
    )

    assert load.normed_by_day == {mon: 8.0, tue: 8.0}
    assert load.unplaced == 10.0
    assert load.normed == 26.0  # 16 ч блока + 10 ч доли
    assert round(load.pct, 1) == round((16.0 + 10.0) / 16.0 * 100, 1)
    assert load.normed_by_type == {"Сопровождение": 16.0, "Минорные": 10.0}


def test_other_team_work_is_listed_per_role(db_session):
    """Строка «другие команды» роли раскрывается задачами её людей: одна задача
    другой команды у двух ролей — две строки. Вид работ — один выбор команды на
    задачу, общий для всех ролей."""
    types, _p, _s, item = _erp(db_session)
    an = make_employee(db_session, "Аналитик", "ERP", role="analyst")
    join_team(db_session, an, "Блок")
    bplan = db_session.execute(select(ResourcePlan).where(ResourcePlan.team == "Блок")).scalar_one()
    book(db_session, bplan, item, an, {d: 4.0 for d in _weekdays("2026-02-02", 5)}, phase="analyst")
    support = types["support_consult"].id
    db_session.add(TeamWorkTypeOverride(team="ERP", backlog_item_id=item.id, work_type_id=support))
    db_session.commit()

    r = nr.team_reserve(db_session, "ERP", *Q)

    assert [(w.role, round(w.hours, 1)) for w in r.other_team_work] == [
        ("dev", 180.0), ("analyst", 20.0),
    ]
    for w in r.other_team_work:
        assert (w.backlog_item_id, w.team, w.work_type_id, w.is_manual) == (
            item.id, "Блок", support, True,
        )
    # Роль строки — тот же ключ, что у роли в сводке запаса.
    assert round(next(x for x in r.roles["analyst"] if x.work_type_id == support).other_teams, 1) == 20.0


def test_personal_zero_normed_leaves_reserve_to_the_other(db_session):
    """Пример спеки 5: у Шутова «свои» нормированные 0% — запас роли и
    остатки видов только у Пряничникова."""
    types, p, s, _item = _erp(db_session)
    _personal(db_session, s, normed={}, involvement=1.0)
    db_session.commit()

    r = nr.team_reserve(db_session, "ERP", *Q)

    norm = r.people[p.id].norm
    rows = {x.work_type_id: x for x in r.roles["dev"]}
    assert round(rows[types["technical_tasks"].id].planned, 2) == round(0.10 * norm, 2)
    assert round(rows[types["organizational"].id].planned, 2) == round(0.10 * norm, 2)
    assert r.people[s.id].share == {}
    assert r.people[s.id].norm == norm  # норма та же, нормированных работ нет
    # Остаток «Орг. вопросов» — весь Пряничникову, не пополам.
    assert round(r.people[p.id].share[types["organizational"].id], 2) == round(0.10 * norm, 2)
    assert round(r.people[p.id].undated, 1) == round(0.45 * norm, 1)


def test_personal_percent_adds_to_role_reserve_and_splits_remainder(db_session):
    """У Шутова своё — только сопровождение 5%: запас сопровождения —
    15% нормы Пряничникова + 5% своей, остаток делится 15 : 5."""
    types, p, s, _item = _erp(db_session)
    support = types["support_consult"].id
    _personal(db_session, s, normed={support: 5})
    db_session.commit()

    r = nr.team_reserve(db_session, "ERP", *Q)

    norm = r.people[p.id].norm
    rows = {x.work_type_id: x for x in r.roles["dev"]}
    assert round(rows[support].planned, 2) == round(0.20 * norm, 2)
    assert {wt: round(h, 2) for wt, h in r.people[s.id].share.items()} == {
        support: round(0.05 * norm, 2)
    }
    assert round(r.people[p.id].share[support], 2) == round(0.15 * norm, 2)
    assert round(r.people[p.id].share[types["minor_change"].id], 2) == round(0.20 * norm, 2)


def test_personal_type_missing_in_role_rules_becomes_role_row(db_session):
    types = _types(db_session)
    p = make_employee(db_session, "Пряничников", "ERP", role="dev")
    s = make_employee(db_session, "Шутов", "ERP", role="dev")
    sc, _plan = make_plan(db_session, "ERP")
    org, minor = types["organizational"].id, types["minor_change"].id
    db_session.add(ScenarioRule(scenario_id=sc.id, role="dev", work_type_id=org, percent_of_norm=10))
    _personal(db_session, s, normed={minor: 20})
    db_session.commit()

    r = nr.team_reserve(db_session, "ERP", *Q)

    rows = {x.work_type_id: x for x in r.roles["dev"]}
    assert set(rows) == {org, minor}
    assert round(rows[minor].planned, 2) == round(0.20 * 512, 2)
    assert {wt: round(h, 2) for wt, h in r.people[s.id].share.items()} == {minor: 102.4}
    assert {wt: round(h, 2) for wt, h in r.people[p.id].share.items()} == {org: 51.2}


def test_team_without_rules_reserve_from_personal_percents(db_session):
    """Правил у команды нет, но у разработчика свои 20% «Сопровождения» — запас
    есть: 20% его нормы, как вычитает база сценария."""
    types = _types(db_session)
    p = make_employee(db_session, "Пряничников", "ERP", role="dev")
    make_employee(db_session, "Шутов", "ERP", role="dev")
    make_plan(db_session, "ERP")
    support = types["support_consult"].id
    _personal(db_session, p, normed={support: 20})
    db_session.commit()

    r = nr.team_reserve(db_session, "ERP", *Q)

    assert r is not None
    [row] = r.roles["dev"]
    assert row.work_type_id == support
    assert round(row.planned, 2) == round(0.20 * 512, 2)
    assert {wt: round(h, 2) for wt, h in r.people[p.id].share.items()} == {support: 102.4}


def test_team_without_rules_and_zero_personal_percents_has_no_reserve(db_session):
    """Без правил и с личными «нет нормированных работ» или 0% — запаса нет."""
    types = _types(db_session)
    p = make_employee(db_session, "Пряничников", "ERP", role="dev")
    s = make_employee(db_session, "Шутов", "ERP", role="dev")
    make_plan(db_session, "ERP")
    _personal(db_session, p, normed={})
    _personal(db_session, s, normed={types["support_consult"].id: 0})
    db_session.commit()

    assert nr.team_reserve(db_session, "ERP", *Q) is None


def test_query_count_with_personal_settings_does_not_grow(db_session):
    types, _p, s, _item = _erp(db_session)
    support = types["support_consult"].id
    _personal(db_session, s, normed={support: 5})
    db_session.commit()
    small = _count_queries(db_session, lambda: nr.team_reserve(db_session, "ERP", *Q))

    for i in range(5):
        e = make_employee(db_session, f"Ещё {i}", "ERP", role="dev")
        _personal(db_session, e, normed={support: i})
    db_session.commit()
    big = _count_queries(db_session, lambda: nr.team_reserve(db_session, "ERP", *Q))

    assert big == small


def _guest_setup(db):
    """P — разработчик ERP (правила 55%, из них «Технические задачи» 10%),
    состоит и в «Блоке», где команда не основная. Броней нет."""
    types = _types(db)
    p = make_employee(db, "Пряничников", "ERP", role="dev")
    s = make_employee(db, "Шутов", "ERP", role="dev")
    join_team(db, p, "Блок")
    sc, _plan = make_plan(db, "ERP")
    _rules(db, sc, types)
    db.commit()
    return types, p, s


def test_guest_normed_excludes_cross_team_type(db_session):
    """Остаток «Технических задач» — время для других команд: в нормированные
    работы гостя он не входит (45% из 55%)."""
    types, p, _s = _guest_setup(db_session)

    by_day = nr.guest_normed_by_day(db_session, [p], [], *Q, D("2026-01-01"), D("2026-03-31"))

    assert round(sum(by_day[p.id].values()), 1) == round(0.45 * 64 * 8.0, 1)
    assert all(d.weekday() < 5 for d in by_day[p.id])


def test_guest_normed_blocked_day_is_whole_day(db_session):
    types, p, _s = _guest_setup(db_session)
    db_session.add(ScheduledBlock(team="ERP", start_date=D("2026-01-05"), end_date=D("2026-01-07"),
                                  reason="Закрытие месяца", work_type_id=types["support_consult"].id))
    db_session.commit()

    by_day = nr.guest_normed_by_day(db_session, [p], [], *Q, D("2026-01-01"), D("2026-03-31"))

    assert [by_day[p.id][D(d)] for d in ("2026-01-05", "2026-01-06", "2026-01-07")] == [8.0, 8.0, 8.0]


def test_guest_normed_empty_without_home_reserve(db_session):
    """У основной команды нет правил — нормированных работ нет, как и раньше."""
    p = make_employee(db_session, "Пряничников", "ERP", role="dev")
    join_team(db_session, p, "Блок")
    db_session.commit()

    assert nr.guest_normed_by_day(db_session, [p], [], *Q, D("2026-01-01"), D("2026-03-31")) == {}
