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

    def test_metric_unknown_calc_kind_rejected(self, admin_client):
        """ВАЖНО 5: опечатка в способе расчёта — 422, а не метрика, которая никогда не считает."""
        payload = _metric_payload()
        payload["calc_kind"] = "raito"
        resp = admin_client.post("/api/v1/kpi-settings/metrics", json=payload)
        assert resp.status_code == 422, resp.text
        assert "способ расчёта" in resp.json()["detail"]

    def test_metric_ratio_requires_denominator(self, admin_client):
        payload = _metric_payload()
        payload["denominator"] = None
        resp = admin_client.post("/api/v1/kpi-settings/metrics", json=payload)
        assert resp.status_code == 422, resp.text
        assert "знаменатель" in resp.json()["detail"]

    def test_metric_norm_to_fact_requires_fact_field(self, admin_client):
        payload = _metric_payload()
        payload["calc_kind"] = "norm_to_fact"
        payload["denominator"] = None
        resp = admin_client.post("/api/v1/kpi-settings/metrics", json=payload)
        assert resp.status_code == 422, resp.text
        assert "факта" in resp.json()["detail"]

    def test_metric_score_to_max_requires_score_fields_and_max(self, admin_client):
        payload = _metric_payload()
        payload["calc_kind"] = "score_to_max"
        payload["denominator"] = None
        resp = admin_client.post("/api/v1/kpi-settings/metrics", json=payload)
        assert resp.status_code == 422, resp.text
        assert "оценок" in resp.json()["detail"]


class TestProfilesCrud:
    def test_profile_weight_sum_validated(self, admin_client):
        # Метрика должна реально существовать: раньше проверка суммы весов
        # шла раньше проверки существования метрик, поэтому этот тест
        # проходил по другой причине — код "quality" ни разу не был заведён
        # в БД, и до проверки суммы дело доходило случайно (см. ревью, ВАЖНО
        # 8 — «сделать честным»).
        admin_client.post("/api/v1/kpi-settings/metrics", json=_metric_payload("quality"))
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

    def test_profile_duplicate_metric_rejected(self, admin_client):
        """ВАЖНО 5: метрика дважды в профиле — понятный 422, а не 500 на уникальном ограничении."""
        admin_client.post("/api/v1/kpi-settings/metrics", json=_metric_payload("quality"))
        resp = admin_client.post("/api/v1/kpi-settings/profiles", json={
            "code": "test", "name": "Тест", "target_pct": 80,
            "metrics": [
                {"metric_code": "quality", "weight": 0.5},
                {"metric_code": "quality", "weight": 0.5},
            ],
        })
        assert resp.status_code == 422, resp.text
        assert "дважды" in resp.json()["detail"]

    def test_profile_negative_weight_rejected(self, admin_client):
        """ВАЖНО 5: отрицательный вес принимался, если сумма всё равно сходилась к 100%."""
        admin_client.post("/api/v1/kpi-settings/metrics", json=_metric_payload("quality"))
        admin_client.post("/api/v1/kpi-settings/metrics", json=_metric_payload("deadlines"))
        resp = admin_client.post("/api/v1/kpi-settings/profiles", json={
            "code": "test", "name": "Тест", "target_pct": 80,
            "metrics": [
                {"metric_code": "quality", "weight": 1.2},
                {"metric_code": "deadlines", "weight": -0.2},
            ],
        })
        assert resp.status_code == 422, resp.text
        assert "0 до 1" in resp.json()["detail"]

    def test_profile_is_default_exclusive(self, admin_client):
        """ВАЖНО 6: признак «по умолчанию» доступен через API и ровно один."""
        admin_client.post("/api/v1/kpi-settings/metrics", json=_metric_payload("quality"))
        first = admin_client.post("/api/v1/kpi-settings/profiles", json={
            "code": "first", "name": "Первый", "target_pct": 80, "is_default": True,
            "metrics": [{"metric_code": "quality", "weight": 1.0}],
        }).json()
        assert first["is_default"] is True

        second = admin_client.post("/api/v1/kpi-settings/profiles", json={
            "code": "second", "name": "Второй", "target_pct": 80, "is_default": True,
            "metrics": [{"metric_code": "quality", "weight": 1.0}],
        }).json()
        assert second["is_default"] is True

        listed = {p["code"]: p for p in admin_client.get("/api/v1/kpi-settings/profiles").json()}
        assert listed["first"]["is_default"] is False
        assert listed["second"]["is_default"] is True

    def test_delete_profile_assigned_to_role_rejected(self, admin_client, db_session):
        from app.models import Employee

        admin_client.post("/api/v1/kpi-settings/metrics", json=_metric_payload("quality"))
        created = admin_client.post("/api/v1/kpi-settings/profiles", json={
            "code": "analyst", "name": "Аналитик", "role_code": "analyst", "target_pct": 80,
            "metrics": [{"metric_code": "quality", "weight": 1.0}],
        }).json()
        db_session.add(Employee(jira_account_id="e1", display_name="Сотрудник", role="analyst"))
        db_session.commit()

        resp = admin_client.delete(f"/api/v1/kpi-settings/profiles/{created['id']}")
        assert resp.status_code == 409
        assert "роли" in resp.json()["detail"]

    def test_delete_default_profile_rejected(self, admin_client):
        admin_client.post("/api/v1/kpi-settings/metrics", json=_metric_payload("quality"))
        created = admin_client.post("/api/v1/kpi-settings/profiles", json={
            "code": "fallback", "name": "Запасной", "target_pct": 80, "is_default": True,
            "metrics": [{"metric_code": "quality", "weight": 1.0}],
        }).json()

        resp = admin_client.delete(f"/api/v1/kpi-settings/profiles/{created['id']}")
        assert resp.status_code == 409
        assert "умолчанию" in resp.json()["detail"]

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

    def test_save_norms_rejects_quarter_out_of_range(self, admin_client):
        """ВАЖНО 5: квартал норматива не был ограничен диапазоном (принимал отрицательные)."""
        resp = admin_client.put("/api/v1/kpi-settings/norms", json=[
            {"team": "Платежи", "year": 2026, "quarter": -1, "norm_value": 70.0},
        ])
        assert resp.status_code == 422


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

    def test_save_general_rejects_bad_time_format(self, admin_client):
        """ВАЖНО 5: время отсечки словами раньше сохранялось как есть, движок молча
        подставлял полдень по умолчанию."""
        resp = admin_client.put("/api/v1/kpi-settings/general", json={
            "excluded_statuses": ["Отменено"], "worklog_deadline_days": 1,
            "worklog_deadline_time": "после обеда", "empty_policy": "redistribute",
        })
        assert resp.status_code == 422
        assert "ЧЧ:ММ" in resp.json()["detail"]

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


class TestAdminOnly:
    """ВАЖНО 8: справочники раздела — только для администратора.

    Шаблон — как в ``tests/test_admin_usage_endpoints.py``: не глобальный
    bypass-фикстурой (она подставляет админа всем тестам), а прямая замена
    ``get_current_user``/``require_admin`` на реального не-админа.
    """

    def test_metrics_forbidden_for_non_admin(self, testclient_db_session):
        import uuid

        from fastapi import HTTPException
        from fastapi.testclient import TestClient

        from app.core.auth_deps import get_current_user, require_admin
        from app.database import get_db
        from app.main import app
        from app.models import User, UserRole

        manager = User(
            id=str(uuid.uuid4()), email=f"{uuid.uuid4()}@test", password_hash="x",
            display_name="Руководитель", role=UserRole.manager, is_active=True,
        )
        testclient_db_session.add(manager)
        testclient_db_session.commit()

        app.dependency_overrides[get_db] = lambda: testclient_db_session
        app.dependency_overrides[get_current_user] = lambda: manager

        def _require_admin_impl():
            if manager.role != UserRole.admin:
                raise HTTPException(status_code=403, detail="Только для администратора")
            return manager

        app.dependency_overrides[require_admin] = _require_admin_impl
        try:
            client = TestClient(app)
            resp = client.get("/api/v1/kpi-settings/metrics")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()
