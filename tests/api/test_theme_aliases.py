"""Tests for theme alias CRUD + merge integration + threshold setting endpoint."""
import pytest
from datetime import date
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.issue import Issue
from app.models.issue_classification import IssueClassification
from app.models.mandatory_work_type import MandatoryWorkType
from app.models.project import Project
from app.models.theme import Theme
from app.models.work_type_report_snapshot import WorkTypeReportSnapshot


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session):
    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def work_type(db_session):
    wt = MandatoryWorkType(
        code="test_aliases_wt", label="Test", is_active=True, sort_order=0,
    )
    db_session.add(wt)
    db_session.commit()
    return wt


def test_add_alias_endpoint(client, db_session, work_type):
    theme = Theme(work_type_id=work_type.id, name="Себестоимость")
    db_session.add(theme)
    db_session.commit()
    theme_id = theme.id

    r = client.post(
        f"/api/v1/work-type-report/themes/{theme_id}/aliases",
        json={"alias": "Таможенная стоимость"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["theme_id"] == theme_id
    assert "Таможенная стоимость" in body["aliases"]


def test_add_alias_is_idempotent(client, db_session, work_type):
    theme = Theme(work_type_id=work_type.id, name="X")
    theme.aliases = ["alpha"]
    db_session.add(theme)
    db_session.commit()
    theme_id = theme.id

    r = client.post(
        f"/api/v1/work-type-report/themes/{theme_id}/aliases",
        json={"alias": "alpha"},
    )
    assert r.status_code == 200
    assert r.json()["aliases"].count("alpha") == 1


def test_delete_alias_endpoint(client, db_session, work_type):
    theme = Theme(work_type_id=work_type.id, name="X")
    theme.aliases = ["alpha", "beta"]
    db_session.add(theme)
    db_session.commit()
    theme_id = theme.id

    r = client.delete(
        f"/api/v1/work-type-report/themes/{theme_id}/aliases",
        params={"alias": "alpha"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "alpha" not in body["aliases"]
    assert "beta" in body["aliases"]


def test_delete_unknown_alias_is_noop(client, db_session, work_type):
    theme = Theme(work_type_id=work_type.id, name="X")
    theme.aliases = ["beta"]
    db_session.add(theme)
    db_session.commit()
    theme_id = theme.id

    r = client.delete(
        f"/api/v1/work-type-report/themes/{theme_id}/aliases",
        params={"alias": "unknown"},
    )
    assert r.status_code == 200
    assert r.json()["aliases"] == ["beta"]


def test_add_alias_to_missing_theme_404(client):
    r = client.post(
        "/api/v1/work-type-report/themes/00000000-0000-0000-0000-000000000000/aliases",
        json={"alias": "x"},
    )
    assert r.status_code == 404


def test_merge_candidate_adds_alias_and_recomputes_embedding(
    client, db_session, work_type,
):
    theme = Theme(work_type_id=work_type.id, name="Себестоимость")
    db_session.add(theme)
    db_session.commit()
    theme_id = theme.id

    project = Project(jira_project_id="P1", key="PRJ", name="Proj")
    db_session.add(project)
    db_session.commit()

    issue = Issue(
        jira_issue_id="iss-1",
        key="PRJ-1",
        project_id=project.id,
        summary="Расчёт таможенной стоимости",
        issue_type="Task",
        status="Done",
    )
    db_session.add(issue)
    db_session.commit()

    cls = IssueClassification(
        issue_id=issue.id,
        work_type_id=work_type.id,
        candidate_name="Таможенная стоимость",
        input_hash="h",
        dictionary_version=1,
    )
    db_session.add(cls)
    db_session.commit()

    snap = WorkTypeReportSnapshot(
        work_type_id=work_type.id,
        year=2026, quarter=2,
        start_date=date(2026, 4, 1), end_date=date(2026, 6, 30),
        team_set_hash="x", team_set_json="[]", snapshot_data="{}",
        dictionary_version=1,
    )
    db_session.add(snap)
    db_session.commit()
    snap_id = snap.id

    r = client.post(
        "/api/v1/work-type-report/candidates/merge",
        json={
            "snapshot_id": snap_id,
            "proposed_name": "Таможенная стоимость",
            "target_theme_id": theme_id,
        },
    )
    assert r.status_code == 200, r.text

    db_session.expire_all()
    t = db_session.get(Theme, theme_id)
    assert "Таможенная стоимость" in t.aliases
    assert t.embedding is not None
    assert t.embedding_model_version is not None


def test_threshold_get_default(client):
    r = client.get("/api/v1/work-type-report/settings/embedding-threshold")
    assert r.status_code == 200
    assert r.json()["threshold"] == pytest.approx(0.78)


def test_threshold_put_and_get_roundtrip(client):
    r = client.put(
        "/api/v1/work-type-report/settings/embedding-threshold",
        json={"threshold": 0.82},
    )
    assert r.status_code == 200, r.text
    assert r.json()["threshold"] == pytest.approx(0.82)

    r = client.get("/api/v1/work-type-report/settings/embedding-threshold")
    assert r.json()["threshold"] == pytest.approx(0.82)


def test_threshold_rejects_out_of_range(client):
    r = client.put(
        "/api/v1/work-type-report/settings/embedding-threshold",
        json={"threshold": 1.5},
    )
    assert r.status_code == 422
