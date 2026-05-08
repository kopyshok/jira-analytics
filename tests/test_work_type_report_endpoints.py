"""Work-type report API: build, get, candidates, manual-classify, layouts."""
import pytest
from datetime import date, datetime
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models.mandatory_work_type import MandatoryWorkType
from app.models.category import Category
from app.models.theme import Theme
from app.models.project import Project
from app.models.issue import Issue
from app.models.employee import Employee
from app.models.worklog import Worklog
from app.models.issue_classification import IssueClassification
from app.services.work_type_report_service import WorkTypeReportService


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session, monkeypatch):
    def _get_db():
        yield db_session
    app.dependency_overrides[get_db] = _get_db

    # Stub LLM provider so build_report doesn't try to reach the real one.
    def _no_provider(db):
        return None
    monkeypatch.setattr(
        "app.api.endpoints.work_type_report.get_llm_provider", _no_provider,
    )
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def setup(db_session):
    wt = MandatoryWorkType(code="support_consult", label="Сопр", sort_order=1)
    db_session.add(wt); db_session.commit()
    cat = Category(code="support_consultation", label="Сопровождение", work_type_id=wt.id)
    db_session.add(cat); db_session.commit()
    proj = Project(jira_project_id="P", key="PROJ", name="Proj")
    db_session.add(proj); db_session.commit()
    emp = Employee(jira_account_id="u1", display_name="Иванов И.", team="Платформа", role="analyst")
    db_session.add(emp); db_session.commit()
    issue = Issue(jira_issue_id="i1", key="PROJ-1", summary="x",
                  issue_type="Task", status="Done", project_id=proj.id,
                  assigned_category="support_consultation",
                  category="support_consultation", team="Платформа")
    db_session.add(issue); db_session.commit()
    db_session.add(Worklog(jira_worklog_id="w1", issue_id=issue.id, employee_id=emp.id,
                           hours=4.0, time_spent_seconds=14400, started_at=datetime(2026, 4, 5)))
    db_session.commit()
    return {"wt": wt, "issue": issue, "emp": emp}


def test_build_report_succeeds_without_provider(client, setup):
    r = client.post("/api/v1/work-type-report", json={
        "work_type_id": setup["wt"].id, "year": 2026, "quarter": 2, "month": 4,
        "teams": [], "force_refresh": False,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["work_type_id"] == setup["wt"].id
    assert body["data"]["totals"]["hours"] >= 4.0


def test_get_report_returns_cached(client, setup):
    client.post("/api/v1/work-type-report", json={
        "work_type_id": setup["wt"].id, "year": 2026, "quarter": 2, "month": 4,
        "teams": [], "force_refresh": False,
    })
    r = client.get(f"/api/v1/work-type-report?work_type_id={setup['wt'].id}&year=2026&quarter=2&month=4")
    assert r.status_code == 200


def test_accept_candidate_creates_theme(client, setup, db_session):
    """Pre-seed a snapshot + classification with candidate_name."""
    # Build a snapshot first
    r = client.post("/api/v1/work-type-report", json={
        "work_type_id": setup["wt"].id, "year": 2026, "quarter": 2, "month": 4,
        "teams": [], "force_refresh": False,
    })
    snap_id = r.json()["snapshot_id"]
    # Manually inject a candidate classification
    cls = IssueClassification(
        issue_id=setup["issue"].id, work_type_id=setup["wt"].id,
        theme_id=None, candidate_name="Кандидат A",
        input_hash="h", dictionary_version=setup["wt"].theme_dict_version,
    )
    db_session.add(cls); db_session.commit()

    r = client.post("/api/v1/work-type-report/candidates/accept", json={
        "snapshot_id": snap_id, "proposed_name": "Кандидат A",
        "color": "#00c9c8",
    })
    assert r.status_code == 200, r.text
    db_session.refresh(cls)
    assert cls.theme_id is not None
    assert cls.candidate_name is None


def test_manual_classify_updates(client, setup, db_session):
    theme = Theme(work_type_id=setup["wt"].id, name="Manual Theme")
    db_session.add(theme); db_session.commit()
    r = client.post("/api/v1/work-type-report/manual-classify", json={
        "issue_id": setup["issue"].id, "work_type_id": setup["wt"].id,
        "theme_id": theme.id, "contribution_text": "manual",
    })
    assert r.status_code == 200
    cls = db_session.execute(
        __import__("sqlalchemy").select(IssueClassification).where(
            IssueClassification.issue_id == setup["issue"].id,
            IssueClassification.work_type_id == setup["wt"].id,
        )
    ).scalar_one()
    assert cls.theme_id == theme.id
    assert cls.contribution_text == "manual"
    assert cls.prompt_version == "manual"


def test_layout_crud(client, setup):
    # Empty list
    r = client.get(f"/api/v1/work-type-report/layouts?work_type_id={setup['wt'].id}")
    assert r.status_code == 200
    assert r.json() == []
    # Create
    r = client.post("/api/v1/work-type-report/layouts", json={
        "work_type_id": setup["wt"].id, "name": "Мой layout",
        "grouping_dims": ["theme", "employee", "issue"],
        "is_default": True,
    })
    assert r.status_code == 201, r.text
    lid = r.json()["id"]
    # List
    r = client.get(f"/api/v1/work-type-report/layouts?work_type_id={setup['wt'].id}")
    layouts = r.json()
    assert len(layouts) == 1 and layouts[0]["is_default"] is True
    # Update
    r = client.patch(f"/api/v1/work-type-report/layouts/{lid}", json={"name": "Renamed"})
    assert r.status_code == 200 and r.json()["name"] == "Renamed"
    # Delete
    r = client.delete(f"/api/v1/work-type-report/layouts/{lid}")
    assert r.status_code == 200
    r = client.get(f"/api/v1/work-type-report/layouts?work_type_id={setup['wt'].id}")
    assert r.json() == []


def test_layout_default_singleton_per_user_wt(client, setup):
    """Setting is_default=True on a new layout clears the previous default."""
    r1 = client.post("/api/v1/work-type-report/layouts", json={
        "work_type_id": setup["wt"].id, "name": "L1",
        "grouping_dims": ["theme"], "is_default": True,
    })
    r2 = client.post("/api/v1/work-type-report/layouts", json={
        "work_type_id": setup["wt"].id, "name": "L2",
        "grouping_dims": ["employee"], "is_default": True,
    })
    layouts = client.get(f"/api/v1/work-type-report/layouts?work_type_id={setup['wt'].id}").json()
    defaults = [l for l in layouts if l["is_default"]]
    assert len(defaults) == 1 and defaults[0]["id"] == r2.json()["id"]


def test_export_xlsx_returns_blob(client, setup):
    r = client.post("/api/v1/work-type-report", json={
        "work_type_id": setup["wt"].id, "year": 2026, "quarter": 2, "month": 4,
        "teams": [], "force_refresh": False,
    })
    snap_id = r.json()["snapshot_id"]
    r = client.get(f"/api/v1/work-type-report/export/{snap_id}.xlsx")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument")
    assert len(r.content) > 200  # non-empty xlsx
