"""API заблокированных периодов: вид работ обязателен, подписи в списке."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.database import get_db
from app.main import app
from app.models import (
    Employee,
    MandatoryWorkType,
    Role,
    ScheduledBlock,
    ScheduledBlockEmployee,
    ScheduledBlockRole,
)

BASE = "/api/v1/resource-planning/scheduled-blocks"


@pytest.fixture
def client(db_session):
    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_block_crud_with_work_type_and_labels(client, db_session):
    wt = MandatoryWorkType(code="support_consult", label="Сопровождение и консультация",
                           subtracts_from_pool=True)
    foreign = MandatoryWorkType(code="other_foreign", label="Прочие / Чужие", subtracts_from_pool=False)
    role = Role(code="analyst", label="Аналитик")
    emp = Employee(display_name="Иванов", jira_account_id="acc-iv", role="analyst")
    db_session.add_all([wt, foreign, role, emp])
    db_session.commit()
    base = {"team": "ERP", "start_date": "2026-10-05", "end_date": "2026-10-07", "reason": "Закрытие месяца"}

    assert client.post(BASE, json=base).status_code == 422
    bad = client.post(BASE, json={**base, "work_type_id": foreign.id})
    assert bad.status_code == 422
    assert bad.json()["detail"] == "Выберите вид нормированных работ"
    assert client.post(BASE, json={**base, "work_type_id": "нет-такого"}).status_code == 422
    r = client.post(BASE, json={**base, "work_type_id": wt.id, "role_ids": [role.id],
                                "employee_ids": [emp.id]})
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["work_type_id"] == wt.id
    assert out["work_type_label"] == "Сопровождение и консультация"
    assert out["role_labels"] == ["Аналитик"]
    assert out["employee_names"] == ["Иванов"]

    listed = client.get(BASE, params={"team": "ERP"}).json()
    assert listed[0]["role_labels"] == ["Аналитик"]
    assert listed[0]["work_type_label"] == "Сопровождение и консультация"
    assert client.patch(f"{BASE}/{out['id']}", json={"work_type_id": None}).status_code == 422
    assert client.patch(f"{BASE}/{out['id']}",
                        json={"work_type_id": foreign.id}).status_code == 422
    patched = client.patch(f"{BASE}/{out['id']}", json={"employee_ids": []})
    assert patched.status_code == 200, patched.text
    assert patched.json()["employee_names"] == []
    assert patched.json()["work_type_id"] == wt.id


def test_old_block_without_work_type_is_listed_and_needs_type_on_edit(client, db_session):
    """Период без вида (до выпуска) виден в списке; изменить его можно, только
    указав вид работ (спека 4.1: вид обязателен при создании и изменении)."""
    wt = MandatoryWorkType(code="organizational", label="Орг. вопросы", subtracts_from_pool=True)
    block = ScheduledBlock(team="ERP", start_date=date(2026, 10, 5), end_date=date(2026, 10, 7),
                           reason="Тренинг")
    db_session.add_all([wt, block])
    db_session.commit()

    [row] = client.get(BASE, params={"team": "ERP"}).json()
    assert row["work_type_id"] is None
    assert row["work_type_label"] is None
    r = client.patch(f"{BASE}/{block.id}", json={"reason": "Обучение"})
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == "Выберите вид нормированных работ"
    db_session.expire_all()
    assert db_session.get(ScheduledBlock, block.id).reason == "Тренинг"

    r = client.patch(f"{BASE}/{block.id}", json={"reason": "Обучение", "work_type_id": wt.id})
    assert r.status_code == 200, r.text
    assert (r.json()["reason"], r.json()["work_type_id"]) == ("Обучение", wt.id)


def test_list_labels_in_constant_queries(client, db_session, engine):
    """Подписи списка — тремя запросами на любой объём, без запроса на период."""
    wt = MandatoryWorkType(code="support_consult", label="Сопровождение", subtracts_from_pool=True)
    roles = [Role(code=f"r{i}", label=f"Роль {i}") for i in range(3)]
    emps = [Employee(display_name=f"Сотрудник {i}", jira_account_id=f"acc-{i}") for i in range(3)]
    db_session.add_all([wt, *roles, *emps])
    db_session.flush()

    def add_block(i):
        b = ScheduledBlock(team="ERP", start_date=date(2026, 10, 1 + i),
                           end_date=date(2026, 10, 1 + i), reason="x", work_type_id=wt.id)
        b.roles = [ScheduledBlockRole(role_id=roles[i].id)]
        b.employees = [ScheduledBlockEmployee(employee_id=emps[i].id)]
        db_session.add(b)

    def count_list_queries():
        db_session.expire_all()
        n = 0

        def _count(*_a, **_k):
            nonlocal n
            n += 1

        event.listen(engine, "before_cursor_execute", _count)
        try:
            r = client.get(BASE, params={"team": "ERP"})
        finally:
            event.remove(engine, "before_cursor_execute", _count)
        assert r.status_code == 200
        return n, r.json()

    add_block(0)
    db_session.commit()
    one, _ = count_list_queries()
    add_block(1)
    add_block(2)
    db_session.commit()
    three, rows = count_list_queries()

    assert three == one
    assert [r["employee_names"] for r in rows] == [["Сотрудник 0"], ["Сотрудник 1"], ["Сотрудник 2"]]
    assert [r["role_labels"] for r in rows] == [["Роль 0"], ["Роль 1"], ["Роль 2"]]


def test_list_shows_whom_team_block_does_not_apply(client, db_session):
    """Список периодов называет, на кого период команды не действует: у них в
    этом месяце свой период того же вида по роли."""
    from tests.services.xteam_factory import make_employee

    wt = MandatoryWorkType(code="support_x", label="Сопровождение", subtracts_from_pool=True)
    role = Role(code="analyst", label="Аналитик")
    db_session.add_all([wt, role])
    db_session.flush()
    make_employee(db_session, "Фокеева", "ERP", role="analyst")
    make_employee(db_session, "Шутов", "ERP", role="dev")
    db_session.commit()
    base = {"team": "ERP", "reason": "Закрытие месяца", "work_type_id": wt.id}
    assert client.post(BASE, json={**base, "start_date": "2026-10-05", "end_date": "2026-10-07",
                                   "role_ids": [role.id]}).status_code == 201
    r = client.post(BASE, json={**base, "reason": "Весь октябрь",
                                "start_date": "2026-10-01", "end_date": "2026-10-31"})
    assert r.status_code == 201, r.text

    by_reason = {b["reason"]: b for b in client.get(BASE, params={"team": "ERP"}).json()}
    assert by_reason["Весь октябрь"]["not_applied"] == [
        {"employee_id": by_reason["Весь октябрь"]["not_applied"][0]["employee_id"],
         "employee_name": "Фокеева", "month": "2026-10-01", "by": "role"},
    ]
    assert by_reason["Закрытие месяца"]["not_applied"] == []
