"""Тесты API справочников раздела KPI: метрики, профили, нормативы, общие правила, атрибуты."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models import Project


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
def admin_client(db_session):
    def _get_db():
        yield db_session
    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _metric_payload(code: str = "quality") -> dict:
    return {
        "code": code,
        "name": "Качество выпуска",
        "calc_kind": "ratio",
        "invert": True,
        "cap_at_100": True,
        "numerator": {
            "unit": "issues", "person_field": "linked_issue_author", "period_window": "closed_in",
            "conditions": [{"attr": "environment", "op": "eq", "value": "PROD"}],
        },
        "denominator": {
            "unit": "issues", "person_field": "author", "period_window": "closed_in",
            "conditions": [],
        },
    }


class TestMetricsCrud:
    def test_create_list_metric(self, admin_client):
        resp = admin_client.post("/api/v1/kpi-settings/metrics", json=_metric_payload())
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["code"] == "quality"
        assert body["numerator"]["conditions"][0]["attr"] == "environment"

        listed = admin_client.get("/api/v1/kpi-settings/metrics").json()
        assert any(m["code"] == "quality" for m in listed)

    def test_create_metric_duplicate_code_rejected(self, admin_client):
        admin_client.post("/api/v1/kpi-settings/metrics", json=_metric_payload())
        resp = admin_client.post("/api/v1/kpi-settings/metrics", json=_metric_payload())
        assert resp.status_code == 409

    def test_update_metric(self, admin_client):
        created = admin_client.post("/api/v1/kpi-settings/metrics", json=_metric_payload()).json()
        payload = _metric_payload()
        payload["name"] = "Качество выпуска (обновлено)"
        resp = admin_client.put(f"/api/v1/kpi-settings/metrics/{created['id']}", json=payload)
        assert resp.status_code == 200
        assert resp.json()["name"] == "Качество выпуска (обновлено)"

    def test_update_metric_not_found(self, admin_client):
        resp = admin_client.put("/api/v1/kpi-settings/metrics/missing-id", json=_metric_payload())
        assert resp.status_code == 404

    def test_delete_metric_in_use_rejected(self, admin_client):
        metric = admin_client.post("/api/v1/kpi-settings/metrics", json=_metric_payload()).json()
        admin_client.post("/api/v1/kpi-settings/profiles", json={
            "code": "analyst", "name": "Аналитик", "role_code": "analyst", "target_pct": 80,
            "metrics": [{"metric_code": "quality", "weight": 1.0}],
        })
        resp = admin_client.delete(f"/api/v1/kpi-settings/metrics/{metric['id']}")
        assert resp.status_code == 409

    def test_delete_metric_not_in_use(self, admin_client):
        metric = admin_client.post("/api/v1/kpi-settings/metrics", json=_metric_payload()).json()
        resp = admin_client.delete(f"/api/v1/kpi-settings/metrics/{metric['id']}")
        assert resp.status_code == 200


class TestProfilesCrud:
    def test_profile_weight_sum_validated(self, admin_client):
        resp = admin_client.post("/api/v1/kpi-settings/profiles", json={
            "code": "test", "name": "Тест", "role_code": "analyst", "target_pct": 80,
            "metrics": [{"metric_code": "quality", "weight": 0.5}],
        })
        assert resp.status_code == 422
        assert "весов" in resp.json()["detail"]

    def test_profile_created_with_full_weight_sum(self, admin_client):
        admin_client.post("/api/v1/kpi-settings/metrics", json=_metric_payload("quality"))
        admin_client.post("/api/v1/kpi-settings/metrics", json=_metric_payload("deadlines"))
        resp = admin_client.post("/api/v1/kpi-settings/profiles", json={
            "code": "analyst", "name": "Аналитик", "role_code": "analyst", "target_pct": 80,
            "metrics": [
                {"metric_code": "quality", "weight": 0.6},
                {"metric_code": "deadlines", "weight": 0.4},
            ],
        })
        assert resp.status_code == 201, resp.text
        assert len(resp.json()["metrics"]) == 2

    def test_profile_unknown_metric_code_404(self, admin_client):
        resp = admin_client.post("/api/v1/kpi-settings/profiles", json={
            "code": "analyst", "name": "Аналитик", "target_pct": 80,
            "metrics": [{"metric_code": "nope", "weight": 1.0}],
        })
        assert resp.status_code == 404

    def test_update_profile_replaces_metrics(self, admin_client):
        admin_client.post("/api/v1/kpi-settings/metrics", json=_metric_payload("quality"))
        admin_client.post("/api/v1/kpi-settings/metrics", json=_metric_payload("deadlines"))
        created = admin_client.post("/api/v1/kpi-settings/profiles", json={
            "code": "analyst", "name": "Аналитик", "target_pct": 80,
            "metrics": [{"metric_code": "quality", "weight": 1.0}],
        }).json()

        resp = admin_client.put(f"/api/v1/kpi-settings/profiles/{created['id']}", json={
            "code": "analyst", "name": "Аналитик", "target_pct": 80,
            "metrics": [{"metric_code": "deadlines", "weight": 1.0}],
        })
        assert resp.status_code == 200
        codes = [m["metric_code"] for m in resp.json()["metrics"]]
        assert codes == ["deadlines"]

    def test_delete_profile(self, admin_client):
        admin_client.post("/api/v1/kpi-settings/metrics", json=_metric_payload("quality"))
        created = admin_client.post("/api/v1/kpi-settings/profiles", json={
            "code": "analyst", "name": "Аналитик", "target_pct": 80,
            "metrics": [{"metric_code": "quality", "weight": 1.0}],
        }).json()
        resp = admin_client.delete(f"/api/v1/kpi-settings/profiles/{created['id']}")
        assert resp.status_code == 200
        assert admin_client.get("/api/v1/kpi-settings/profiles").json() == []


class TestNorms:
    def test_save_and_list_norms(self, admin_client):
        resp = admin_client.put("/api/v1/kpi-settings/norms", json=[
            {"team": "Платежи", "year": 2026, "quarter": 3, "norm_value": 70.0},
        ])
        assert resp.status_code == 200, resp.text
        assert resp.json()[0]["norm_value"] == 70.0

        listed = admin_client.get("/api/v1/kpi-settings/norms?year=2026&quarter=3").json()
        assert listed[0]["team"] == "Платежи"

    def test_save_norms_updates_existing_pair(self, admin_client):
        admin_client.put("/api/v1/kpi-settings/norms", json=[
            {"team": "Платежи", "year": 2026, "quarter": 3, "norm_value": 70.0},
        ])
        resp = admin_client.put("/api/v1/kpi-settings/norms", json=[
            {"team": "Платежи", "year": 2026, "quarter": 3, "norm_value": 65.0},
        ])
        assert resp.status_code == 200
        listed = admin_client.get("/api/v1/kpi-settings/norms?year=2026&quarter=3").json()
        assert len(listed) == 1
        assert listed[0]["norm_value"] == 65.0


class TestGeneral:
    def test_get_general_defaults(self, admin_client):
        resp = admin_client.get("/api/v1/kpi-settings/general")
        assert resp.status_code == 200
        body = resp.json()
        assert body["excluded_statuses"] == ["Отменено"]
        assert body["empty_policy"] == "redistribute"

    def test_save_general_rejects_bad_policy(self, admin_client):
        resp = admin_client.put("/api/v1/kpi-settings/general", json={
            "excluded_statuses": ["Отменено"], "worklog_deadline_days": 1,
            "worklog_deadline_time": "12:00", "empty_policy": "bogus",
        })
        assert resp.status_code == 422

    def test_save_general_persists(self, admin_client):
        resp = admin_client.put("/api/v1/kpi-settings/general", json={
            "excluded_statuses": ["Отменено", "Отклонено"], "worklog_deadline_days": 2,
            "worklog_deadline_time": "15:30", "empty_policy": "zero",
        })
        assert resp.status_code == 200
        got = admin_client.get("/api/v1/kpi-settings/general").json()
        assert got["worklog_deadline_time"] == "15:30"
        assert "Отклонено" in got["excluded_statuses"]
        assert got["empty_policy"] == "zero"


class TestConditionValidationOnSave:
    """BLOCKER 2: опечатка в условии не сохраняется, а падает понятной ошибкой."""

    def test_unknown_attr_rejected_with_422(self, admin_client):
        payload = _metric_payload()
        payload["numerator"]["conditions"] = [
            {"attr": "environmentt", "op": "eq", "value": "PROD"},
        ]
        resp = admin_client.post("/api/v1/kpi-settings/metrics", json=payload)
        assert resp.status_code == 422, resp.text
        assert "атрибут" in resp.json()["detail"]

    def test_unknown_person_field_rejected_with_422(self, admin_client):
        payload = _metric_payload()
        payload["numerator"]["person_field"] = "autor"
        resp = admin_client.post("/api/v1/kpi-settings/metrics", json=payload)
        assert resp.status_code == 422, resp.text
        assert "кто считается" in resp.json()["detail"]


class TestAttributes:
    def test_attributes_dictionary_exposed(self, admin_client):
        resp = admin_client.get("/api/v1/kpi-settings/attributes")
        assert resp.status_code == 200
        body = resp.json()
        attrs = {a["key"] for a in body["attributes"]}
        assert "project_key" in attrs and "environment" in attrs
        assert "author" in body["person_fields"]

    def test_attributes_pull_choices_from_db(self, admin_client, db_session):
        db_session.add(Project(jira_project_id="1", key="OS", name="1С"))
        db_session.commit()
        resp = admin_client.get("/api/v1/kpi-settings/attributes")
        attrs = {a["key"]: a for a in resp.json()["attributes"]}
        assert "OS" in attrs["project_key"]["choices"]
