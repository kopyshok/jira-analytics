"""Модуль чтения распределения сотрудника по группам."""

from datetime import date

from app.models import Employee, EmployeeSubgroupShare, EmployeeTeam, Team, TeamSubgroup
from app.services import subgroup_shares as ss
from app.services.subgroup_shares import ShareRecord

A, B = "g-a", "g-b"
Q_START, Q_END = date(2026, 10, 1), date(2026, 12, 31)


def rec(valid_from, *shares):
    return ShareRecord(valid_from, tuple(shares))


def test_record_on_picks_latest_started():
    records = [rec(None, (A, 100)), rec(date(2026, 11, 15), (B, 100))]
    assert ss.single_group_on(records, date(2026, 11, 14)) == A
    assert ss.single_group_on(records, date(2026, 11, 15)) == B


def test_record_on_before_first_dated_record_is_none():
    records = [rec(date(2026, 11, 1), (A, 100))]
    assert ss.record_on(records, date(2026, 10, 31)) is None
    assert ss.shares_on(records, date(2026, 10, 31)) == {}


def test_shared_person_has_no_single_group():
    records = [rec(None, (A, 60), (B, 40))]
    assert ss.single_group_on(records, date(2026, 10, 1)) is None
    assert ss.shares_on(records, date(2026, 10, 1)) == {A: 0.6, B: 0.4}


def test_split_hours_without_group_goes_to_empty_key():
    assert ss.split_hours([], date(2026, 10, 1), 8.0) == {"": 8.0}
    assert ss.split_hours([rec(None, (A, 60), (B, 40))], date(2026, 10, 1), 10.0) == {
        A: 6.0, B: 4.0,
    }


def test_segments_and_groups_between():
    records = [rec(None, (A, 100)), rec(date(2026, 11, 15), (B, 100))]
    assert ss.segments(records, Q_START, Q_END) == [
        (Q_START, date(2026, 11, 14), records[0]),
        (date(2026, 11, 15), Q_END, records[1]),
    ]
    assert ss.groups_between(records, Q_START, Q_END) == {A, B}
    assert ss.groups_between(records, date(2026, 12, 1), Q_END) == {B}


def test_group_labels():
    transfer = [rec(None, (A, 100)), rec(date(2026, 11, 15), (B, 100))]
    assert ss.group_label(transfer, A, Q_START, Q_END) == "до 15.11"
    assert ss.group_label(transfer, B, Q_START, Q_END) == "с 15.11"
    split = [rec(None, (A, 60), (B, 40))]
    assert ss.group_label(split, A, Q_START, Q_END) == "60%"
    whole = [rec(None, (A, 100))]
    assert ss.group_label(whole, A, Q_START, Q_END) == ""


def test_group_label_shows_percent_on_full_span_when_group_had_partial_span():
    """Была на 40%, потом получила остаток — 100% пишем явно, а не молчим."""
    records = [rec(None, (A, 40), (B, 60)), rec(date(2026, 11, 16), (A, 100))]
    assert ss.group_label(records, A, Q_START, Q_END) == "40% до 16.11, 100% с 16.11"


def test_distribution_label_keeps_plain_name_for_whole_quarter():
    names = {A: "Ломбард", B: "РФМ"}
    assert ss.distribution_label([rec(None, (A, 100))], Q_START, Q_END, names) == "Ломбард"
    assert ss.distribution_label(
        [rec(None, (A, 60), (B, 40))], Q_START, Q_END, names
    ) == "Ломбард 60% · РФМ 40%"
    assert ss.distribution_label(
        [rec(None, (A, 100)), rec(date(2026, 11, 15), (B, 100))], Q_START, Q_END, names
    ) == "Ломбард до 15.11 · РФМ с 15.11"
    assert ss.distribution_label([], Q_START, Q_END, names) is None


def _team(db):
    team = Team(id="t1", name="T", has_subgroups=True)
    db.add(team)
    db.flush()
    db.add_all([
        TeamSubgroup(id=A, team_id="t1", name="Ломбард", sort_order=1),
        TeamSubgroup(id=B, team_id="t1", name="РФМ", sort_order=2),
    ])
    for eid in ("e1", "e2", "e3"):
        db.add(Employee(id=eid, jira_account_id=f"acc-{eid}", display_name=eid, is_active=True))
        db.add(EmployeeTeam(employee_id=eid, team="T", is_primary=True))
    db.flush()


def test_load_team_groups_rows_into_records(db_session):
    _team(db_session)
    db_session.add_all([
        EmployeeSubgroupShare(employee_id="e1", team="T", valid_from=None, subgroup_id=A, percent=100),
        EmployeeSubgroupShare(employee_id="e1", team="T", valid_from=date(2026, 11, 15), subgroup_id=A, percent=40),
        EmployeeSubgroupShare(employee_id="e1", team="T", valid_from=date(2026, 11, 15), subgroup_id=B, percent=60),
    ])
    db_session.commit()

    records = ss.load_team(db_session, "T")["e1"]
    assert records == [
        rec(None, (A, 100)),
        rec(date(2026, 11, 15), (B, 60), (A, 40)),
    ]
    assert ss.team_subgroups(db_session, "T") == [(A, "Ломбард"), (B, "РФМ")]


def test_ungrouped_members(db_session):
    _team(db_session)
    db_session.add_all([
        EmployeeSubgroupShare(employee_id="e1", team="T", valid_from=None, subgroup_id=A, percent=100),
        # e2 получает группу только с ноября — октябрь без группы
        EmployeeSubgroupShare(employee_id="e2", team="T", valid_from=date(2026, 11, 1), subgroup_id=B, percent=100),
    ])
    db_session.commit()

    assert ss.ungrouped_members(db_session, "T", Q_START, Q_END) == ["e2", "e3"]
    assert ss.ungrouped_members(db_session, "T", date(2026, 11, 1), Q_END) == ["e3"]


def test_ungrouped_members_empty_without_division(db_session):
    db_session.add(Team(id="t2", name="Plain", has_subgroups=False))
    db_session.add(Employee(id="e9", jira_account_id="acc-9", display_name="e9", is_active=True))
    db_session.add(EmployeeTeam(employee_id="e9", team="Plain", is_primary=True))
    db_session.commit()
    assert ss.ungrouped_members(db_session, "Plain", Q_START, Q_END) == []


def test_ungrouped_members_excludes_inactive(db_session):
    _team(db_session)
    db_session.query(Employee).filter_by(id="e3").one().is_active = False
    db_session.add(EmployeeSubgroupShare(employee_id="e1", team="T", valid_from=None, subgroup_id=A, percent=100))
    db_session.commit()

    assert ss.ungrouped_members(db_session, "T", Q_START, Q_END) == ["e2"]


def test_ungrouped_members_not_flagged_when_group_starts_on_join_date(db_session):
    """e2 приходит в команду 15.11 и сразу получает долю — не «без группы»."""
    _team(db_session)
    db_session.query(EmployeeTeam).filter_by(employee_id="e2", team="T").one().joined_at = date(2026, 11, 15)
    db_session.add_all([
        EmployeeSubgroupShare(employee_id="e1", team="T", valid_from=None, subgroup_id=A, percent=100),
        EmployeeSubgroupShare(employee_id="e2", team="T", valid_from=date(2026, 11, 15), subgroup_id=B, percent=100),
    ])
    db_session.commit()

    assert ss.ungrouped_members(db_session, "T", Q_START, Q_END) == ["e3"]


def test_quarter_labels_clips_to_membership(db_session):
    _team(db_session)
    # e1 покинул команду 15.10, доля появляется только с 01.11 — весь его
    # период участия в команде остаётся без группы, подписи нет.
    db_session.query(EmployeeTeam).filter_by(employee_id="e1", team="T").one().left_at = date(2026, 10, 15)
    # e2 приходит в команду 15.11 и сразу получает долю целиком — «с 15.11»
    # было бы лишним, так как это и есть его первый день в команде.
    db_session.query(EmployeeTeam).filter_by(employee_id="e2", team="T").one().joined_at = date(2026, 11, 15)
    db_session.add_all([
        EmployeeSubgroupShare(employee_id="e1", team="T", valid_from=date(2026, 11, 1), subgroup_id=A, percent=100),
        EmployeeSubgroupShare(employee_id="e2", team="T", valid_from=date(2026, 11, 15), subgroup_id=A, percent=100),
        # e3 — весь квартал в команде, перевод с 15.11.
        EmployeeSubgroupShare(employee_id="e3", team="T", valid_from=None, subgroup_id=A, percent=100),
        EmployeeSubgroupShare(employee_id="e3", team="T", valid_from=date(2026, 11, 15), subgroup_id=B, percent=100),
    ])
    db_session.commit()

    labels = ss.quarter_labels(db_session, "T", Q_START, Q_END)

    assert "e1" not in labels
    assert labels["e2"] == "Ломбард"
    assert labels["e3"] == "Ломбард до 15.11 · РФМ с 15.11"


def test_load_all_groups_by_employee_and_team(db_session):
    _team(db_session)
    db_session.add(Team(id="t2", name="U", has_subgroups=True))
    db_session.flush()
    db_session.add(TeamSubgroup(id="g-u", team_id="t2", name="U-группа", sort_order=1))
    db_session.add(EmployeeTeam(employee_id="e1", team="U", is_primary=False))
    db_session.flush()
    db_session.add_all([
        EmployeeSubgroupShare(employee_id="e1", team="T", valid_from=None, subgroup_id=A, percent=100),
        EmployeeSubgroupShare(employee_id="e1", team="U", valid_from=None, subgroup_id="g-u", percent=100),
        EmployeeSubgroupShare(employee_id="e2", team="T", valid_from=None, subgroup_id=B, percent=100),
    ])
    db_session.commit()

    all_records = ss.load_all(db_session)
    assert set(all_records) == {("e1", "T"), ("e1", "U"), ("e2", "T")}

    filtered = ss.load_all(db_session, ["e1"])
    assert set(filtered) == {("e1", "T"), ("e1", "U")}

    assert ss.load_all(db_session, []) == {}
