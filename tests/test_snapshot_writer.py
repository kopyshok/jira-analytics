"""Тесты SnapshotWriter: создание снапшотов при approve сценария."""
import uuid
from datetime import date as ddate
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import (
    Absence,
    AbsenceReason,
    BacklogItem,
    Employee,
    EmployeeTeam,
    MandatoryWorkType,
    PlanningScenario,
    ProductionCalendarDay,
    Role,
    ScenarioAllocation,
    ScenarioAllocationSnapshot,
    ScenarioCalendarSnapshot,
    ScenarioCapacitySnapshot,
    ScenarioDictionarySnapshot,
    ScenarioNormSnapshot,
    ScenarioRevision,
    ScenarioRule,
    ScenarioRulesSnapshot,
    ScenarioTeamSnapshot,
)
from app.services.snapshot_writer import SnapshotWriter


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def team_setup(db_session: Session):
    """Команда из 2 активных сотрудников + сценарий + одна ревизия."""
    e1 = Employee(
        id="e-1", jira_account_id="j1", display_name="Иванов И.",
        role="analyst", is_active=True,
    )
    e2 = Employee(
        id="e-2", jira_account_id="j2", display_name="Петров П.",
        role="dev", is_active=True,
    )
    db_session.add_all([e1, e2])
    db_session.add_all([
        EmployeeTeam(id="et-1", employee_id="e-1", team="T1", is_primary=True),
        EmployeeTeam(id="et-2", employee_id="e-2", team="T1", is_primary=True),
    ])
    sc = PlanningScenario(
        id="s-1", name="Q2", year=2026, quarter="Q2", team="T1",
        status="draft", external_qa_hours=None,
    )
    db_session.add(sc)
    rev = ScenarioRevision(
        id="r-1", scenario_id="s-1", revision_number=1,
        approved_at=datetime.utcnow(),
    )
    db_session.add(rev)
    db_session.commit()
    return {"scenario": sc, "revision": rev}


def test_write_team_snapshot_copies_active_team_members(
    db_session: Session, team_setup
):
    """write_team_snapshot копирует display_name/role/is_active каждого сотрудника команды."""
    writer = SnapshotWriter(db_session)
    writer.write_team_snapshot(
        revision=team_setup["revision"], scenario=team_setup["scenario"]
    )
    db_session.commit()

    rows = (
        db_session.query(ScenarioTeamSnapshot)
        .filter_by(revision_id="r-1")
        .order_by(ScenarioTeamSnapshot.display_name)
        .all()
    )
    assert len(rows) == 2
    assert rows[0].display_name == "Иванов И."
    assert rows[0].role == "analyst"
    assert rows[1].display_name == "Петров П."
    assert rows[1].role == "dev"
    assert all(r.is_active for r in rows)


def test_write_team_snapshot_no_team_does_nothing(db_session: Session):
    """Сценарий без team → ничего не записывается."""
    sc = PlanningScenario(
        id="s-x", name="X", year=2026, quarter="Q2", team=None,
        status="draft",
    )
    db_session.add(sc)
    rev = ScenarioRevision(
        id="r-x", scenario_id="s-x", revision_number=1,
        approved_at=datetime.utcnow(),
    )
    db_session.add(rev)
    db_session.commit()

    writer = SnapshotWriter(db_session)
    writer.write_team_snapshot(revision=rev, scenario=sc)
    db_session.commit()

    rows = db_session.query(ScenarioTeamSnapshot).filter_by(revision_id="r-x").all()
    assert rows == []


def test_write_team_snapshot_empty_team_does_nothing(db_session: Session):
    """Команда без членов → ничего не записывается."""
    sc = PlanningScenario(
        id="s-y", name="Y", year=2026, quarter="Q2", team="EmptyTeam",
        status="draft",
    )
    db_session.add(sc)
    rev = ScenarioRevision(
        id="r-y", scenario_id="s-y", revision_number=1,
        approved_at=datetime.utcnow(),
    )
    db_session.add(rev)
    db_session.commit()

    writer = SnapshotWriter(db_session)
    writer.write_team_snapshot(revision=rev, scenario=sc)
    db_session.commit()

    rows = db_session.query(ScenarioTeamSnapshot).filter_by(revision_id="r-y").all()
    assert rows == []


def test_write_calendar_snapshot_copies_quarter_days(db_session: Session, team_setup):
    """Календарь Q2: копируются только дни апр+май+июн, июль не попадает."""
    db_session.add(ProductionCalendarDay(
        date=ddate(2026, 4, 1), hours=8.0, is_workday=True, kind="workday", source="manual",
    ))
    db_session.add(ProductionCalendarDay(
        date=ddate(2026, 5, 9), hours=0.0, is_workday=False, kind="holiday", source="manual",
    ))
    db_session.add(ProductionCalendarDay(
        date=ddate(2026, 6, 30), hours=8.0, is_workday=True, kind="workday", source="manual",
    ))
    db_session.add(ProductionCalendarDay(
        date=ddate(2026, 7, 1), hours=8.0, is_workday=True, kind="workday", source="manual",
    ))
    db_session.commit()

    writer = SnapshotWriter(db_session)
    writer.write_calendar_snapshot(
        revision=team_setup["revision"], scenario=team_setup["scenario"]
    )
    db_session.commit()

    rows = db_session.query(ScenarioCalendarSnapshot).filter_by(revision_id="r-1").all()
    dates = sorted(r.date for r in rows)
    assert ddate(2026, 4, 1) in dates
    assert ddate(2026, 5, 9) in dates
    assert ddate(2026, 6, 30) in dates
    assert ddate(2026, 7, 1) not in dates  # вне Q2
    holiday = next(r for r in rows if r.date == ddate(2026, 5, 9))
    assert holiday.kind == "holiday"
    assert holiday.is_workday is False


def test_write_calendar_snapshot_no_quarter_does_nothing(db_session: Session):
    """Сценарий без year/quarter → ничего не пишется."""
    sc = PlanningScenario(
        id="s-x", name="X", year=None, quarter=None, team="T",
        status="draft",
    )
    db_session.add(sc)
    rev = ScenarioRevision(
        id="r-x", scenario_id="s-x", revision_number=1,
        approved_at=datetime.utcnow(),
    )
    db_session.add(rev)
    db_session.commit()

    writer = SnapshotWriter(db_session)
    writer.write_calendar_snapshot(revision=rev, scenario=sc)
    db_session.commit()

    rows = db_session.query(ScenarioCalendarSnapshot).filter_by(revision_id="r-x").all()
    assert rows == []


def test_write_rules_snapshot_copies_scenario_rules(db_session: Session, team_setup):
    """Snapshot копирует scenario_rules сценария + резолвит work_type_label."""
    wt = MandatoryWorkType(
        id="wt-1", code="support", label="Сопровождение",
        is_active=True, sort_order=1, subtracts_from_pool=True,
    )
    db_session.add(wt)
    db_session.add(ScenarioRule(
        id="sr-1", scenario_id="s-1", role="analyst",
        work_type_id="wt-1", percent_of_norm=35.0,
    ))
    db_session.commit()

    writer = SnapshotWriter(db_session)
    writer.write_rules_snapshot(
        revision=team_setup["revision"], scenario=team_setup["scenario"]
    )
    db_session.commit()

    rows = db_session.query(ScenarioRulesSnapshot).filter_by(revision_id="r-1").all()
    assert len(rows) == 1
    assert rows[0].role == "analyst"
    assert rows[0].work_type_id == "wt-1"
    assert rows[0].work_type_label == "Сопровождение"
    assert rows[0].pct_of_norm == 35.0


def test_write_rules_snapshot_no_rules_does_nothing(db_session: Session, team_setup):
    """Сценарий без правил → ничего не пишется."""
    writer = SnapshotWriter(db_session)
    writer.write_rules_snapshot(
        revision=team_setup["revision"], scenario=team_setup["scenario"]
    )
    db_session.commit()

    rows = db_session.query(ScenarioRulesSnapshot).filter_by(revision_id="r-1").all()
    assert rows == []


def test_write_dictionary_snapshot_copies_work_types_roles_and_reasons(
    db_session: Session, team_setup
):
    """Snapshot копирует все work_types, roles, absence_reasons (в т.ч. неактивные)."""
    db_session.add(MandatoryWorkType(
        id="wt-1", code="support", label="Сопровождение",
        is_active=True, sort_order=1, subtracts_from_pool=True,
    ))
    db_session.add(MandatoryWorkType(
        id="wt-2", code="org", label="Орг. вопросы",
        is_active=False, sort_order=2, subtracts_from_pool=True,
    ))
    db_session.add(Role(
        id="ro-1", code="analyst", label="Аналитик",
        sort_order=1, is_active=True,
    ))
    db_session.add(AbsenceReason(
        id="ar-1", code="vacation", label="Отпуск", is_planned=True,
        color="#fff", is_active=True, sort_order=1,
    ))
    db_session.commit()

    writer = SnapshotWriter(db_session)
    writer.write_dictionary_snapshot(revision=team_setup["revision"])
    db_session.commit()

    rows = db_session.query(ScenarioDictionarySnapshot).filter_by(revision_id="r-1").all()
    by_key = {(r.kind, r.original_id): r for r in rows}

    assert ("work_type", "wt-1") in by_key
    assert by_key[("work_type", "wt-1")].label == "Сопровождение"
    assert by_key[("work_type", "wt-1")].extra_json == {
        "subtracts_from_pool": True,
        "is_active": True,
    }
    # Неактивные тоже копируются для readability
    assert ("work_type", "wt-2") in by_key
    assert by_key[("work_type", "wt-2")].extra_json["is_active"] is False

    assert ("role", "ro-1") in by_key
    assert by_key[("role", "ro-1")].label == "Аналитик"
    assert by_key[("role", "ro-1")].code == "analyst"

    assert ("absence_reason", "ar-1") in by_key
    assert by_key[("absence_reason", "ar-1")].label == "Отпуск"
    assert by_key[("absence_reason", "ar-1")].extra_json["is_planned"] is True


def test_write_capacity_snapshot_per_emp_per_month(
    db_session: Session, team_setup
):
    """Capacity snapshot: gross/absence/available/mandatory/project per emp×month."""
    from app.models import Absence, ScenarioCapacitySnapshot

    # Создаём причину отсутствия (reason_id обязателен в Absence)
    ar = AbsenceReason(
        id="ar-cap", code="vacation_cap", label="Отпуск",
        is_planned=True, color=None, is_active=True, sort_order=1,
    )
    db_session.add(ar)

    # Календарь Q2: 3 рабочих дня по 8ч в каждом месяце
    for d in [ddate(2026, 4, 1), ddate(2026, 4, 2), ddate(2026, 4, 3),
              ddate(2026, 5, 1), ddate(2026, 5, 4), ddate(2026, 5, 5),
              ddate(2026, 6, 1), ddate(2026, 6, 2), ddate(2026, 6, 3)]:
        db_session.add(ProductionCalendarDay(
            date=d, hours=8.0, is_workday=True, kind="workday", source="manual",
        ))

    # Иванов (e-1) в отпуске весь май
    db_session.add(Absence(
        id="ab-1", employee_id="e-1",
        start_date=ddate(2026, 5, 1), end_date=ddate(2026, 5, 31),
        reason_id="ar-cap",
    ))

    # Правила: analyst — Сопровождение 35% + Орг 15% = 50% mandatory (subtracts_from_pool)
    db_session.add(MandatoryWorkType(
        id="wt-1", code="support_cap", label="Сопровождение",
        is_active=True, sort_order=1, subtracts_from_pool=True,
    ))
    db_session.add(MandatoryWorkType(
        id="wt-2", code="org_cap", label="Орг",
        is_active=True, sort_order=2, subtracts_from_pool=True,
    ))
    db_session.add(ScenarioRule(
        id="sr-c1", scenario_id="s-1", role="analyst",
        work_type_id="wt-1", percent_of_norm=35.0,
    ))
    db_session.add(ScenarioRule(
        id="sr-c2", scenario_id="s-1", role="analyst",
        work_type_id="wt-2", percent_of_norm=15.0,
    ))
    db_session.commit()

    writer = SnapshotWriter(db_session)
    writer.write_capacity_snapshot(
        revision=team_setup["revision"], scenario=team_setup["scenario"]
    )
    db_session.commit()

    rows = (
        db_session.query(ScenarioCapacitySnapshot)
        .filter_by(revision_id="r-1", employee_id="e-1")
        .order_by(ScenarioCapacitySnapshot.month)
        .all()
    )
    assert len(rows) == 3
    apr, may, jun = rows

    # апрель: 24ч брутто, 0 отсутствий → available=24, mandatory=12, project=12
    assert apr.month == 4
    assert apr.gross_hours == 24.0
    assert apr.absence_hours == 0.0
    assert apr.available_hours == 24.0
    assert apr.mandatory_hours == 12.0
    assert apr.project_hours == 12.0

    # май: 24ч брутто, весь в отсутствии → available=0, mandatory=0, project=0
    assert may.absence_hours == 24.0
    assert may.available_hours == 0.0
    assert may.mandatory_hours == 0.0
    assert may.project_hours == 0.0

    # июнь: 24/0/24/12/12
    assert jun.gross_hours == 24.0
    assert jun.available_hours == 24.0

    # legacy: norm_hours = gross_hours
    assert apr.norm_hours == 24.0


def test_write_norm_snapshot_uses_available_not_gross(
    db_session: Session, team_setup
):
    """Норм. часы = available × pct, НЕ gross × pct (отсутствия учтены)."""
    ar = AbsenceReason(
        id="ar-n1", code="vacation_n1", label="Отпуск",
        is_planned=True, color=None, is_active=True, sort_order=1,
    )
    db_session.add(ar)
    for d in [ddate(2026, 4, 1), ddate(2026, 4, 2),
              ddate(2026, 5, 4), ddate(2026, 5, 5),
              ddate(2026, 6, 1), ddate(2026, 6, 2)]:
        db_session.add(ProductionCalendarDay(
            date=d, hours=8.0, is_workday=True, kind="workday", source="manual",
        ))
    # Иванов (e-1) в отпуске 1-2 апреля (оба рабочих дня апреля)
    db_session.add(Absence(
        id="ab-n1", employee_id="e-1",
        start_date=ddate(2026, 4, 1), end_date=ddate(2026, 4, 2),
        reason_id="ar-n1",
    ))
    db_session.add(MandatoryWorkType(
        id="wt-1", code="support", label="Сопровождение",
        is_active=True, sort_order=1, subtracts_from_pool=True,
    ))
    db_session.add(ScenarioRule(
        id="sr-1", scenario_id="s-1", role="analyst",
        work_type_id="wt-1", percent_of_norm=35.0,
    ))
    db_session.commit()

    writer = SnapshotWriter(db_session)
    writer.write_capacity_snapshot(
        revision=team_setup["revision"], scenario=team_setup["scenario"]
    )
    writer.write_norm_snapshot(
        revision=team_setup["revision"], scenario=team_setup["scenario"]
    )
    db_session.commit()

    apr = db_session.query(ScenarioNormSnapshot).filter_by(
        revision_id="r-1", employee_id="e-1", month=4, work_type_id="wt-1"
    ).one()
    # gross=16, absence=16 (оба дня) → available=0 → norm=0 (НЕ 16×0.35=5.6)
    assert apr.norm_hours == 0.0
    assert apr.is_external is False

    may = db_session.query(ScenarioNormSnapshot).filter_by(
        revision_id="r-1", employee_id="e-1", month=5, work_type_id="wt-1"
    ).one()
    # gross=16, absence=0 → available=16 → norm 16×0.35 = 5.6
    assert may.norm_hours == 5.6


def test_write_norm_snapshot_external_qa(db_session: Session, team_setup):
    """external_qa_hours = 600 → 200/мес × pct правила QA."""
    team_setup["scenario"].external_qa_hours = 600.0
    db_session.commit()
    db_session.add(MandatoryWorkType(
        id="wt-1", code="support", label="Сопровождение",
        is_active=True, sort_order=1, subtracts_from_pool=True,
    ))
    db_session.add(ScenarioRule(
        id="sr-1", scenario_id="s-1", role="qa",
        work_type_id="wt-1", percent_of_norm=35.0,
    ))
    db_session.commit()

    writer = SnapshotWriter(db_session)
    writer.write_capacity_snapshot(
        revision=team_setup["revision"], scenario=team_setup["scenario"]
    )
    writer.write_norm_snapshot(
        revision=team_setup["revision"], scenario=team_setup["scenario"]
    )
    db_session.commit()

    qa_rows = db_session.query(ScenarioNormSnapshot).filter_by(
        revision_id="r-1", is_external=True
    ).all()
    assert len(qa_rows) == 3  # 3 месяца
    for r in qa_rows:
        assert r.employee_id is None
        assert r.role == "qa"
        assert r.work_type_id == "wt-1"
        assert r.norm_hours == 70.0  # 200 × 0.35


def test_write_allocation_snapshot_copies_included_items(
    db_session: Session, team_setup
):
    """write_allocation_snapshot: included=True → 1 строка с полными атрибутами;
    included=False → не попадает в snapshot."""
    # bi-1 included, rich attributes
    bi1 = BacklogItem(
        id="bi-1",
        title="Инициатива А",
        issue_id=None,
        project_id="proj-1",
        customer="ООО Заказчик",
        cost_type="capex",
        impact="high",
        risk="medium",
        priority=1,
        estimate_analyst_hours=40.0,
        estimate_dev_hours=80.0,
        estimate_qa_hours=20.0,
        estimate_opo_hours=10.0,
        opo_analyst_ratio=0.6,
        assignee_employee_id="e-1",
    )
    # bi-2 not included
    bi2 = BacklogItem(
        id="bi-2",
        title="Инициатива Б",
        assignee_employee_id=None,
    )
    db_session.add_all([bi1, bi2])

    al1 = ScenarioAllocation(
        id="al-1",
        scenario_id="s-1",
        backlog_item_id="bi-1",
        included_flag=True,
        sort_order=1.0,
        involvement_coefficient=0.8,
    )
    al2 = ScenarioAllocation(
        id="al-2",
        scenario_id="s-1",
        backlog_item_id="bi-2",
        included_flag=False,
        sort_order=2.0,
    )
    db_session.add_all([al1, al2])
    db_session.commit()

    writer = SnapshotWriter(db_session)
    writer.write_allocation_snapshot(
        revision=team_setup["revision"], scenario=team_setup["scenario"]
    )
    db_session.commit()

    rows = db_session.query(ScenarioAllocationSnapshot).filter_by(revision_id="r-1").all()
    assert len(rows) == 1, "Only included_flag=True allocation should be snapshotted"

    row = rows[0]
    assert row.allocation_id == "al-1"
    assert row.backlog_item_id == "bi-1"
    assert row.title == "Инициатива А"
    assert row.project_id == "proj-1"
    assert row.customer == "ООО Заказчик"
    assert row.cost_type == "capex"
    assert row.impact == "high"
    assert row.risk == "medium"
    assert row.priority == 1
    assert row.estimate_analyst_hours == 40.0
    assert row.estimate_dev_hours == 80.0
    assert row.estimate_qa_hours == 20.0
    assert row.estimate_opo_hours == 10.0
    assert row.opo_analyst_ratio == 0.6
    assert row.assignee_employee_id == "e-1"
    assert row.assignee_role_at_approval == "analyst"  # looked up from Employee
    assert row.sort_order == 1.0
    assert row.included_flag is True
    assert row.involvement_coefficient == 0.8
