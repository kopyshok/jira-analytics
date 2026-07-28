"""Аналитика, режим «Иерархия»: задачи деревом до верхнего родителя."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.services.analytics_service import AnalyticsService
from tests.test_analytics_report import (
    _seed_emp, _seed_issue, _seed_minimal, _seed_project, _seed_worklog,
)


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _leaf_category(data):
    return data.teams[0].roles[0].employees[0].work_types[0].categories[0]


def test_hierarchy_off_keeps_flat_list(db_session):
    _seed_minimal(db_session)
    project = _seed_project(db_session)
    emp = _seed_emp(db_session, "Тест", "Команда A")
    top = _seed_issue(db_session, project, "T-100", "Команда A", None)
    child = _seed_issue(db_session, project, "T-101", "Команда A", "support_consultation")
    child.parent_id = top.id
    db_session.commit()
    _seed_worklog(db_session, child, emp, 4.0)

    data = AnalyticsService(db_session).get_hierarchical_report(
        year=2026, quarter=2, teams=["Команда A"],
    )
    issues = _leaf_category(data).issues
    assert [i.key for i in issues] == ["T-101"]
    assert issues[0].children == []


def test_hierarchy_builds_chain_to_top_parent(db_session):
    _seed_minimal(db_session)
    project = _seed_project(db_session)
    emp = _seed_emp(db_session, "Тест", "Команда A")
    top = _seed_issue(db_session, project, "T-100", "Команда A", None, summary="Проект")
    mid = _seed_issue(db_session, project, "T-110", "Команда A", None, summary="Эпик")
    child = _seed_issue(db_session, project, "T-111", "Команда A", "support_consultation")
    mid.parent_id = top.id
    child.parent_id = mid.id
    db_session.commit()
    _seed_worklog(db_session, child, emp, 4.0)

    data = AnalyticsService(db_session).get_hierarchical_report(
        year=2026, quarter=2, teams=["Команда A"], hierarchy=True,
    )
    cat = _leaf_category(data)
    assert cat.totals.fact_hours == 4.0

    root = cat.issues[0]
    assert (root.key, root.row_kind, root.totals.fact_hours) == ("T-100", "context", 4.0)
    epic = root.children[0]
    assert (epic.key, epic.row_kind, epic.totals.fact_hours) == ("T-110", "context", 4.0)
    leaf = epic.children[0]
    assert (leaf.key, leaf.row_kind, leaf.totals.fact_hours) == ("T-111", "issue", 4.0)
    assert leaf.children == []


def test_parent_with_own_worklogs_gets_own_row(db_session):
    _seed_minimal(db_session)
    project = _seed_project(db_session)
    emp = _seed_emp(db_session, "Тест", "Команда A")
    parent = _seed_issue(db_session, project, "T-200", "Команда A", "support_consultation")
    child = _seed_issue(db_session, project, "T-201", "Команда A", "support_consultation")
    child.parent_id = parent.id
    db_session.commit()
    _seed_worklog(db_session, parent, emp, 3.0)
    _seed_worklog(db_session, child, emp, 5.0)

    data = AnalyticsService(db_session).get_hierarchical_report(
        year=2026, quarter=2, teams=["Команда A"], hierarchy=True,
    )
    cat = _leaf_category(data)
    assert cat.totals.fact_hours == 8.0

    root = cat.issues[0]
    assert root.key == "T-200"
    assert root.row_kind == "issue"
    assert root.totals.fact_hours == 8.0  # сумма ветки, свои часы учтены один раз

    kinds = {(c.key, c.row_kind): c.totals.fact_hours for c in root.children}
    assert kinds[("T-201", "issue")] == 5.0
    assert kinds[("T-200", "own")] == 3.0
