"""Тесты CRUD endpoints capacity rules v2:
 - /mandatory-work-types
 - /capacity/role-rules
 - /capacity/employee-overrides
"""

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models import (
    Employee,
    EmployeeCapacityOverride,
    MandatoryWorkType,
    Role,
    RoleCapacityRule,
)


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
def client(db_session):
    def _get_db():
        yield db_session
    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _seed_roles(db_session):
    """Роли из миграции 025 — валидация role-rules идёт по этой таблице."""
    for code, label in [
        ("analyst", "Аналитик"),
        ("dev", "Программист"),
        ("qa", "Тестировщик"),
        ("consultant", "Консультант"),
        ("other", "Другое"),
    ]:
        db_session.add(Role(code=code, label=label))
    db_session.commit()


@pytest.fixture
def wt(db_session):
    w = MandatoryWorkType(code="tech_debt", label="Технический долг", is_active=True)
    db_session.add(w)
    db_session.commit()
    return w


@pytest.fixture
def employee(db_session):
    e = Employee(id="emp1", jira_account_id="a1", display_name="Dev",
                 is_active=True, role="dev")
    db_session.add(e)
    db_session.commit()
    return e


# ──────────────────── Mandatory work types ────────────────────

class TestMandatoryWorkTypesCRUD:
    def test_list_empty_then_create(self, client):
        assert client.get("/api/v1/mandatory-work-types").json() == []

        res = client.post("/api/v1/mandatory-work-types", json={
            "code": "organizational", "label": "Орг.",
        })
        assert res.status_code == 201
        body = res.json()
        assert body["code"] == "organizational"
        assert body["is_active"] is True
        assert body["sort_order"] == 0

        res2 = client.get("/api/v1/mandatory-work-types")
        assert len(res2.json()) == 1

    def test_unique_code(self, client):
        client.post("/api/v1/mandatory-work-types", json={"code": "x", "label": "X"})
        res = client.post("/api/v1/mandatory-work-types", json={"code": "x", "label": "Other"})
        assert res.status_code == 409

    def test_patch_label_and_sort(self, client, wt):
        res = client.patch(f"/api/v1/mandatory-work-types/{wt.id}", json={
            "label": "Тех. долг", "sort_order": 5,
        })
        assert res.status_code == 200
        assert res.json()["label"] == "Тех. долг"
        assert res.json()["sort_order"] == 5

    def test_delete_blocked_when_referenced(self, client, wt, db_session):
        db_session.add(RoleCapacityRule(
            year=2026, quarter=1, role="dev",
            work_type_id=wt.id, percent_of_norm=10.0,
        ))
        db_session.commit()

        res = client.delete(f"/api/v1/mandatory-work-types/{wt.id}")
        assert res.status_code == 409
        assert "referenced" in res.json()["detail"]

    def test_delete_ok_when_unused(self, client, wt):
        res = client.delete(f"/api/v1/mandatory-work-types/{wt.id}")
        assert res.status_code == 204

    def test_reorder(self, client):
        ids = []
        for i, c in enumerate(["a", "b", "c"]):
            r = client.post("/api/v1/mandatory-work-types",
                             json={"code": c, "label": c, "sort_order": i})
            ids.append(r.json()["id"])
        # invert
        res = client.post("/api/v1/mandatory-work-types/reorder",
                           json={"ids": list(reversed(ids))})
        assert res.status_code == 200
        codes_sorted = [x["code"] for x in res.json()]
        assert codes_sorted == ["c", "b", "a"]


# ──────────────────── Role capacity rules (batch v3) ────────────────────

class TestRoleCapacityRulesCRUD:
    def test_list_then_create(self, client, wt):
        empty = client.get("/api/v1/capacity/role-rules?year=2026&quarter=1").json()
        assert empty == []

        res = client.put(
            "/api/v1/capacity/role-rules/batch?year=2026&quarter=1",
            json={"rules": [
                {"role": "dev", "work_type_id": wt.id, "percent_of_norm": 100.0},
            ]},
        )
        assert res.status_code == 200

        lst = client.get("/api/v1/capacity/role-rules?year=2026&quarter=1").json()
        assert len(lst) == 1

    def test_unknown_role_422(self, client, wt):
        res = client.put(
            "/api/v1/capacity/role-rules/batch?year=2026&quarter=1",
            json={"rules": [
                {"role": "ceo", "work_type_id": wt.id, "percent_of_norm": 100.0},
            ]},
        )
        assert res.status_code == 422
        assert "Unknown role" in res.json()["detail"]

    def test_null_role_accepted(self, client, wt):
        res = client.put(
            "/api/v1/capacity/role-rules/batch?year=2026&quarter=1",
            json={"rules": [
                {"role": None, "work_type_id": wt.id, "percent_of_norm": 100.0},
            ]},
        )
        assert res.status_code == 200
        assert res.json()[0]["role"] is None

    def test_duplicate_in_batch_422(self, client, wt):
        res = client.put(
            "/api/v1/capacity/role-rules/batch?year=2026&quarter=1",
            json={"rules": [
                {"role": "analyst", "work_type_id": wt.id, "percent_of_norm": 50.0},
                {"role": "analyst", "work_type_id": wt.id, "percent_of_norm": 50.0},
            ]},
        )
        assert res.status_code == 422
        assert "Duplicate rule" in res.json()["detail"]

    def test_sum_not_100_returns_422(self, client, wt):
        res = client.put(
            "/api/v1/capacity/role-rules/batch?year=2026&quarter=1",
            json={"rules": [
                {"role": "dev", "work_type_id": wt.id, "percent_of_norm": 50.0},
            ]},
        )
        assert res.status_code == 422
        errors = res.json()["detail"]["errors"]
        assert errors[0]["role"] == "dev"
        assert errors[0]["sum"] == 50.0
        assert errors[0]["expected"] == 100.0

    def test_batch_updates_existing_rule(self, client, wt, db_session):
        # Seed a rule directly in DB with percent=60 (invalid alone but we're testing replace).
        db_session.add(RoleCapacityRule(
            year=2026, quarter=1, role="qa",
            work_type_id=wt.id, percent_of_norm=60.0,
        ))
        db_session.commit()

        # Atomic replace — submit a new percent; the old rule is wiped first.
        res = client.put(
            "/api/v1/capacity/role-rules/batch?year=2026&quarter=1",
            json={"rules": [
                {"role": "qa", "work_type_id": wt.id, "percent_of_norm": 100.0},
            ]},
        )
        assert res.status_code == 200

        lst = client.get("/api/v1/capacity/role-rules?year=2026&quarter=1").json()
        assert len(lst) == 1
        assert lst[0]["percent_of_norm"] == 100.0

    def test_batch_removes_rule_by_omission(self, client, wt):
        # Seed a rule.
        client.put(
            "/api/v1/capacity/role-rules/batch?year=2026&quarter=1",
            json={"rules": [
                {"role": "other", "work_type_id": wt.id, "percent_of_norm": 100.0},
            ]},
        )
        assert len(client.get("/api/v1/capacity/role-rules?year=2026&quarter=1").json()) == 1

        # Empty batch clears all rules for this (year, quarter).
        res = client.put(
            "/api/v1/capacity/role-rules/batch?year=2026&quarter=1",
            json={"rules": []},
        )
        assert res.status_code == 200
        assert client.get("/api/v1/capacity/role-rules?year=2026&quarter=1").json() == []

    def test_copy_to_quarter_happy_path(self, client, wt, db_session):
        # Seed source quarter directly via DB to avoid endpoint coupling.
        db_session.add(RoleCapacityRule(
            year=2026, quarter=1, role="dev",
            work_type_id=wt.id, percent_of_norm=100.0,
        ))
        db_session.commit()

        res = client.post("/api/v1/capacity/role-rules/copy-to-quarter", json={
            "from_year": 2026, "from_quarter": 1,
            "to_year": 2026, "to_quarter": 2,
        })
        assert res.status_code == 201
        assert res.json()["created"] == 1

    def test_copy_to_quarter_conflict_409(self, client, wt, db_session):
        for q in (1, 2):
            db_session.add(RoleCapacityRule(
                year=2026, quarter=q, role="dev",
                work_type_id=wt.id, percent_of_norm=100.0,
            ))
        db_session.commit()

        res = client.post("/api/v1/capacity/role-rules/copy-to-quarter", json={
            "from_year": 2026, "from_quarter": 1,
            "to_year": 2026, "to_quarter": 2,
        })
        assert res.status_code == 409
        assert "conflicts" in res.json()["detail"]


# ──────────────────── Employee overrides (batch v3) ────────────────────

class TestEmployeeCapacityOverridesCRUD:
    def test_list_filters(self, client, wt, employee):
        res = client.put(
            "/api/v1/capacity/employee-overrides/batch?year=2026&quarter=1",
            json={"employee_rules": [
                {"employee_id": employee.id, "rules": [
                    {"work_type_id": wt.id, "percent_of_norm": 100.0},
                ]},
            ]},
        )
        assert res.status_code == 200

        listed = client.get(
            f"/api/v1/capacity/employee-overrides?year=2026&quarter=1&employee_id={employee.id}",
        )
        assert listed.status_code == 200
        assert len(listed.json()) == 1

    def test_unknown_employee_404(self, client, wt):
        res = client.put(
            "/api/v1/capacity/employee-overrides/batch?year=2026&quarter=1",
            json={"employee_rules": [
                {"employee_id": "does-not-exist", "rules": [
                    {"work_type_id": wt.id, "percent_of_norm": 100.0},
                ]},
            ]},
        )
        assert res.status_code == 404
        assert "Unknown employee_id" in res.json()["detail"]

    def test_duplicate_in_batch_422(self, client, wt, employee):
        res = client.put(
            "/api/v1/capacity/employee-overrides/batch?year=2026&quarter=1",
            json={"employee_rules": [
                {"employee_id": employee.id, "rules": [
                    {"work_type_id": wt.id, "percent_of_norm": 50.0},
                    {"work_type_id": wt.id, "percent_of_norm": 50.0},
                ]},
            ]},
        )
        assert res.status_code == 422
        assert "Duplicate rule" in res.json()["detail"]

    def test_sum_not_100_returns_422(self, client, wt, employee):
        res = client.put(
            "/api/v1/capacity/employee-overrides/batch?year=2026&quarter=1",
            json={"employee_rules": [
                {"employee_id": employee.id, "rules": [
                    {"work_type_id": wt.id, "percent_of_norm": 25.0},
                ]},
            ]},
        )
        assert res.status_code == 422
        errors = res.json()["detail"]["errors"]
        assert errors[0]["employee_id"] == employee.id
        assert errors[0]["sum"] == 25.0

    def test_batch_updates_and_removes_overrides(self, client, wt, employee):
        # Seed override.
        client.put(
            "/api/v1/capacity/employee-overrides/batch?year=2026&quarter=1",
            json={"employee_rules": [
                {"employee_id": employee.id, "rules": [
                    {"work_type_id": wt.id, "percent_of_norm": 100.0},
                ]},
            ]},
        )
        listed = client.get(
            f"/api/v1/capacity/employee-overrides?year=2026&quarter=1&employee_id={employee.id}",
        ).json()
        assert len(listed) == 1
        assert listed[0]["percent_of_norm"] == 100.0

        # Empty rules for this employee — clears all their overrides on (year, quarter).
        removed = client.put(
            "/api/v1/capacity/employee-overrides/batch?year=2026&quarter=1",
            json={"employee_rules": [
                {"employee_id": employee.id, "rules": []},
            ]},
        )
        assert removed.status_code == 200
        listed_after = client.get(
            f"/api/v1/capacity/employee-overrides?year=2026&quarter=1&employee_id={employee.id}",
        ).json()
        assert listed_after == []
