"""GET /planning/involvement-defaults/fact — фактическая вовлечённость."""

from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import (
    Category, Employee, EmployeeTeam, Issue, MandatoryWorkType, Project, Worklog,
)
from app.services.involvement_fact import last_completed_quarter

URL = "/api/v1/planning/involvement-defaults/fact"


@pytest.fixture
def client(testclient_db_session):
    def _get_db():
        yield testclient_db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def seeded(testclient_db_session):
    db = testclient_db_session
    wt = MandatoryWorkType(code="project", label="Проекты и развитие")
    db.add(wt)
    db.flush()
    db.add(Category(code="quarterly_tasks", label="Квартальные", work_type_id=wt.id))
    proj = Project(jira_project_id="p1", key="PRJ", name="Проект")
    db.add(proj)
    db.flush()
    project_issue = Issue(
        jira_issue_id="i1", key="PRJ-1", project_id=proj.id, summary="Проектная",
        issue_type="Task", status="В работе", category="quarterly_tasks",
    )
    other_issue = Issue(
        jira_issue_id="i2", key="PRJ-2", project_id=proj.id, summary="Прочая",
        issue_type="Task", status="В работе",
    )
    an = Employee(jira_account_id="a1", display_name="Аналитикова", role="analyst")
    db.add_all([project_issue, other_issue, an])
    db.flush()
    db.add(EmployeeTeam(employee_id=an.id, team="Альфа", is_primary=True))
    for n, (issue, day, hours) in enumerate([
        (project_issue, date(2026, 7, 6), 30.0),
        (other_issue, date(2026, 7, 6), 10.0),
        (other_issue, date(2026, 7, 7), 8.0),
        (project_issue, date(2026, 9, 1), 20.0),
    ]):
        db.add(Worklog(
            jira_worklog_id=f"w{n}", issue_id=issue.id, employee_id=an.id,
            started_at=datetime.combine(day, datetime.min.time()),
            hours=hours, time_spent_seconds=int(hours * 3600),
        ))
    db.commit()


def test_fact_for_quarter(client, seeded):
    r = client.get(URL, params={"teams": "Альфа,Бета", "year": 2026, "quarter": 3})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["year"], body["quarter"], body["months"]) == (2026, 3, [7, 8, 9])
    alpha, beta = body["teams"]
    assert alpha["team"] == "Альфа" and beta == {"team": "Бета", "people": [], "roles": []}

    [person] = alpha["people"]
    assert person["name"] == "Аналитикова" and person["role"] == "analyst"
    assert [m["month"] for m in person["months"]] == [7, 8, 9]
    jul, aug, _ = person["months"]
    # 6 июля — 30 ч проект + 10 ч прочее; 7 июля без проекта в факт не входит.
    assert jul["fact"] == 0.75 and jul["logged_hours"] == 48.0 and jul["norm_hours"] == 184.0
    assert jul["project_days"] == 1 and jul["project_day_hours"] == 40.0
    assert aug["fact"] is None and aug["logged_of_norm"] == 0.0
    assert person["total"]["fact"] == round(50 / 60, 4)

    [role] = alpha["roles"]
    assert role["role"] == "analyst" and role["people"] == 1
    assert role["total"]["project_hours"] == 50.0
    assert role["total"]["logged_of_norm"] == round(68 / 528, 4)


def test_default_is_last_completed_quarter(client, seeded):
    r = client.get(URL, params={"teams": "Альфа"})
    assert r.status_code == 200, r.text
    assert (r.json()["year"], r.json()["quarter"]) == last_completed_quarter(date.today())


def test_teams_required(client):
    assert client.get(URL).status_code == 422
    assert client.get(URL, params={"teams": " , "}).status_code == 422


@pytest.mark.parametrize("params", [{"year": 2026}, {"quarter": 3}])
def test_year_and_quarter_together(client, params):
    """Только год или только квартал — ошибка, а не тихая подмена периода."""
    assert client.get(URL, params={"teams": "Альфа", **params}).status_code == 422
