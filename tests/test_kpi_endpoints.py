"""Тесты API раздела KPI: отчёт, сводка по командам, расшифровка, тренд, утверждение месяца."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models import AppSetting, Employee, EmployeeTeam, Issue, Project
from app.services.kpi.seed import seed_defaults


@pytest.fixture
def db_session():
    """StaticPool in-memory DB so the TestClient thread shares the same connection."""
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
def client(db_session):
    def _get_db():
        yield db_session
    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def team_with_analyst(db_session):
    """Команда «Платежи» с одним аналитиком и профилем оценки по умолчанию."""
    seed_defaults(db_session)
    db_session.commit()

    project = Project(jira_project_id="1", key="OS", name="1С")
    db_session.add(project)
    emp = Employee(jira_account_id="acc-1", display_name="Иванов И.", team="Платежи", role="analyst")
    db_session.add(emp)
    db_session.commit()
    db_session.add(EmployeeTeam(employee_id=emp.id, team="Платежи", is_primary=True))
    db_session.commit()
    return {"project": project, "employee": emp}


class TestReport:
    @pytest.mark.no_auth_bypass
    def test_report_requires_auth(self, client):
        resp = client.get("/api/v1/kpi/report?year=2026&month=7")
        assert resp.status_code in (401, 403)

    def test_report_returns_rows_and_summary(self, client, team_with_analyst):
        resp = client.get("/api/v1/kpi/report?year=2026&month=7&teams=Платежи")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "rows" in body and "summary" in body
        assert [r["employee_name"] for r in body["rows"]] == ["Иванов И."]
        assert "avg_total" in body["summary"]

    def test_report_defaults_to_all_teams_when_omitted(self, client, team_with_analyst):
        resp = client.get("/api/v1/kpi/report?year=2026&month=7")
        assert resp.status_code == 200
        assert [r["employee_name"] for r in resp.json()["rows"]] == ["Иванов И."]


class TestTeamsSummary:
    def test_teams_summary_lists_team_with_delta(self, client, team_with_analyst):
        resp = client.get("/api/v1/kpi/teams-summary?year=2026&month=7")
        assert resp.status_code == 200, resp.text
        rows = resp.json()["rows"]
        assert any(r["team"] == "Платежи" for r in rows)
        row = next(r for r in rows if r["team"] == "Платежи")
        assert "delta" in row


class TestBreakdown:
    def test_breakdown_unknown_metric_404(self, client, team_with_analyst):
        resp = client.get(
            "/api/v1/kpi/breakdown"
            "?account_id=acc-1&metric_code=does-not-exist&year=2026&month=7"
        )
        assert resp.status_code == 404

    def test_breakdown_returns_task_lists_with_jira_links(self, client, db_session, team_with_analyst):
        project = team_with_analyst["project"]
        from datetime import datetime

        released = Issue(
            jira_issue_id="r1", key="OS-100", summary="Задача", issue_type="Задача",
            status="ГОТОВО", status_category="done", resolution="Готово",
            resolved_at=datetime(2026, 7, 10), project_id=project.id,
            reporter_account_id="acc-1", team="Платежи",
        )
        db_session.add(released)
        db_session.add(AppSetting(key="jira_base_url", value="https://itgri.atlassian.net"))
        db_session.commit()

        resp = client.get(
            "/api/v1/kpi/breakdown"
            "?account_id=acc-1&metric_code=quality&year=2026&month=7&teams=Платежи"
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["metric_code"] == "quality"
        assert any(t["key"] == "OS-100" for t in body["denominator"])
        item = next(t for t in body["denominator"] if t["key"] == "OS-100")
        assert item["url"] == "https://itgri.atlassian.net/browse/OS-100"


class TestTrend:
    def test_trend_returns_requested_number_of_points(self, client, team_with_analyst):
        resp = client.get(
            "/api/v1/kpi/trend?account_id=acc-1&year=2026&month=7&months=3&teams=Платежи"
        )
        assert resp.status_code == 200, resp.text
        points = resp.json()["points"]
        assert len(points) == 3
        assert [p["month"] for p in points] == [5, 6, 7]

    def test_trend_unknown_employee_404(self, client, team_with_analyst):
        resp = client.get("/api/v1/kpi/trend?account_id=missing&year=2026&month=7")
        assert resp.status_code == 404


class TestApproval:
    def test_approve_and_read_back(self, client, team_with_analyst):
        resp = client.post(
            "/api/v1/kpi/approve", json={"team": "Платежи", "year": 2026, "month": 7}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["approved_by"]

        got = client.get("/api/v1/kpi/approval?team=Платежи&year=2026&month=7")
        assert got.status_code == 200
        assert got.json()["approved"] is True
        assert got.json()["approved_by"]

    def test_approval_not_yet_approved(self, client, team_with_analyst):
        resp = client.get("/api/v1/kpi/approval?team=Платежи&year=2026&month=7")
        assert resp.status_code == 200
        assert resp.json()["approved"] is False

    def test_reapprove_overwrites_snapshot_without_error(self, client, team_with_analyst):
        first = client.post(
            "/api/v1/kpi/approve", json={"team": "Платежи", "year": 2026, "month": 7}
        )
        assert first.status_code == 200
        second = client.post(
            "/api/v1/kpi/approve", json={"team": "Платежи", "year": 2026, "month": 7}
        )
        assert second.status_code == 200


class TestExport:
    def test_export_xlsx_returns_workbook(self, client, team_with_analyst):
        resp = client.get("/api/v1/kpi/export.xlsx?year=2026&month=7&teams=Платежи")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert len(resp.content) > 0
