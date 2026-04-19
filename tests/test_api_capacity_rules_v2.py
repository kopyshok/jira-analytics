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


@pytest.fixture
def wt(db_session):
    w = MandatoryWorkType(code="tech_debt", label="Технический долг", is_active=True)
    db_session.add(w)
    db_session.commit()
    return w


@pytest.fixture
def employee(db_session):
    e = Employee(id="emp1", jira_account_id="a1", display_name="Dev",
                 is_active=True, role="programmer")
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
            year=2026, quarter=1, role="programmer",
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


# ──────────────────── Role capacity rules ────────────────────

class TestRoleCapacityRulesCRUD:
    def test_list_then_create(self, client, wt):
        empty = client.get("/api/v1/capacity/role-rules?year=2026&quarter=1").json()
        assert empty == []

        res = client.post("/api/v1/capacity/role-rules", json={
            "year": 2026, "quarter": 1, "role": "programmer",
            "work_type_id": wt.id, "percent_of_norm": 10.0,
        })
        assert res.status_code == 201

        lst = client.get("/api/v1/capacity/role-rules?year=2026&quarter=1").json()
        assert len(lst) == 1

    def test_unknown_role_422(self, client, wt):
        res = client.post("/api/v1/capacity/role-rules", json={
            "year": 2026, "quarter": 1, "role": "ceo",
            "work_type_id": wt.id, "percent_of_norm": 5.0,
        })
        assert res.status_code == 422

    def test_null_role_accepted(self, client, wt):
        res = client.post("/api/v1/capacity/role-rules", json={
            "year": 2026, "quarter": 1, "role": None,
            "work_type_id": wt.id, "percent_of_norm": 3.0,
        })
        assert res.status_code == 201
        assert res.json()["role"] is None

    def test_duplicate_scope_409(self, client, wt):
        body = {"year": 2026, "quarter": 1, "role": "analyst",
                "work_type_id": wt.id, "percent_of_norm": 10.0}
        client.post("/api/v1/capacity/role-rules", json=body)
        res = client.post("/api/v1/capacity/role-rules", json=body)
        assert res.status_code == 409

    def test_patch_percent(self, client, wt):
        created = client.post("/api/v1/capacity/role-rules", json={
            "year": 2026, "quarter": 1, "role": "tester",
            "work_type_id": wt.id, "percent_of_norm": 5.0,
        }).json()
        res = client.patch(
            f"/api/v1/capacity/role-rules/{created['id']}",
            json={"percent_of_norm": 7.5},
        )
        assert res.status_code == 200
        assert res.json()["percent_of_norm"] == 7.5

    def test_delete(self, client, wt):
        created = client.post("/api/v1/capacity/role-rules", json={
            "year": 2026, "quarter": 1, "role": "consultant",
            "work_type_id": wt.id, "percent_of_norm": 5.0,
        }).json()
        res = client.delete(f"/api/v1/capacity/role-rules/{created['id']}")
        assert res.status_code == 204

    def test_copy_to_quarter_happy_path(self, client, wt):
        client.post("/api/v1/capacity/role-rules", json={
            "year": 2026, "quarter": 1, "role": "programmer",
            "work_type_id": wt.id, "percent_of_norm": 10.0,
        })
        res = client.post("/api/v1/capacity/role-rules/copy-to-quarter", json={
            "from_year": 2026, "from_quarter": 1,
            "to_year": 2026, "to_quarter": 2,
        })
        assert res.status_code == 201
        assert res.json()["created"] == 1

    def test_copy_to_quarter_conflict_409(self, client, wt):
        for q in (1, 2):
            client.post("/api/v1/capacity/role-rules", json={
                "year": 2026, "quarter": q, "role": "programmer",
                "work_type_id": wt.id, "percent_of_norm": 10.0,
            })
        res = client.post("/api/v1/capacity/role-rules/copy-to-quarter", json={
            "from_year": 2026, "from_quarter": 1,
            "to_year": 2026, "to_quarter": 2,
        })
        assert res.status_code == 409
        assert "conflicts" in res.json()["detail"]


# ──────────────────── Employee overrides ────────────────────

class TestEmployeeCapacityOverridesCRUD:
    def test_list_filters(self, client, wt, employee):
        client.post("/api/v1/capacity/employee-overrides", json={
            "year": 2026, "quarter": 1, "employee_id": employee.id,
            "work_type_id": wt.id, "percent_of_norm": 20.0,
        })
        res = client.get(
            f"/api/v1/capacity/employee-overrides?year=2026&quarter=1&employee_id={employee.id}",
        )
        assert res.status_code == 200
        assert len(res.json()) == 1

    def test_unknown_employee_404(self, client, wt):
        res = client.post("/api/v1/capacity/employee-overrides", json={
            "year": 2026, "quarter": 1, "employee_id": "does-not-exist",
            "work_type_id": wt.id, "percent_of_norm": 20.0,
        })
        assert res.status_code == 404

    def test_duplicate_scope_409(self, client, wt, employee):
        body = {"year": 2026, "quarter": 1, "employee_id": employee.id,
                "work_type_id": wt.id, "percent_of_norm": 20.0}
        client.post("/api/v1/capacity/employee-overrides", json=body)
        res = client.post("/api/v1/capacity/employee-overrides", json=body)
        assert res.status_code == 409

    def test_patch_and_delete(self, client, wt, employee):
        created = client.post("/api/v1/capacity/employee-overrides", json={
            "year": 2026, "quarter": 1, "employee_id": employee.id,
            "work_type_id": wt.id, "percent_of_norm": 20.0,
        }).json()
        patched = client.patch(
            f"/api/v1/capacity/employee-overrides/{created['id']}",
            json={"percent_of_norm": 25.0},
        )
        assert patched.status_code == 200
        assert patched.json()["percent_of_norm"] == 25.0

        removed = client.delete(
            f"/api/v1/capacity/employee-overrides/{created['id']}",
        )
        assert removed.status_code == 204
