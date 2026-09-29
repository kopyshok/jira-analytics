"""API личных настроек сотрудника: вовлечённость и свои нормированные работы."""
from datetime import date
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import EmployeePersonalNormed, EmployeePersonalSetting, MandatoryWorkType
from app.services.event_bus import get_event_bus
from tests.services.xteam_factory import join_team, make_employee

URL = "/api/v1/planning/personal-settings"
EVENT = {"type": "entity_changed", "entities": ["planning", "resource_planning"]}


@pytest.fixture
def bus():
    return AsyncMock()


@pytest.fixture
def client(testclient_db_session, bus):
    app.dependency_overrides[get_db] = lambda: testclient_db_session
    app.dependency_overrides[get_event_bus] = lambda: bus
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def data(testclient_db_session):
    db = testclient_db_session
    org = MandatoryWorkType(code="organizational", label="Орг. вопросы", sort_order=1,
                            subtracts_from_pool=True)
    sup = MandatoryWorkType(code="support_consult", label="Сопровождение", sort_order=0,
                            subtracts_from_pool=True)
    other = MandatoryWorkType(code="other_foreign", label="Прочие / Чужие", sort_order=9,
                              subtracts_from_pool=False)
    db.add_all([org, sup, other])
    p = make_employee(db, "Пряничников", "ERP", role="dev")
    a = make_employee(db, "Арбузов", "ERP", role="analyst")
    left = make_employee(db, "Бывший", "Блок", role="dev")
    join_team(db, left, "ERP", joined_at=date(2025, 1, 1), left_at=date(2026, 1, 1))
    stranger = make_employee(db, "Чужой", "Блок", role="dev")
    db.commit()
    return {"org": org.id, "sup": sup.id, "other": other.id, "p": p.id, "a": a.id,
            "left": left.id, "stranger": stranger.id}


def _body(emp, year=2026, quarter=4, involvement=None, normed=None):
    return {
        "employee_id": emp, "effective_year": year, "effective_quarter": quarter,
        "involvement": involvement, "normed_custom": normed is not None,
        "normed": [{"work_type_id": k, "percent_of_norm": v} for k, v in (normed or {}).items()],
    }


def test_create_returns_row_and_publishes(client, bus, data):
    r = client.post(URL, json=_body(data["p"], involvement=1.0,
                                    normed={data["org"]: 10, data["sup"]: 5}))

    assert r.status_code == 201, r.text
    body = r.json()
    assert body["employee_id"] == data["p"]
    assert body["employee_name"] == "Пряничников"
    assert body["employee_role"] == "dev"
    assert (body["effective_year"], body["effective_quarter"]) == (2026, 4)
    assert body["involvement"] == 1.0
    assert body["normed_custom"] is True
    # Виды — в порядке справочника.
    assert body["normed"] == [
        {"work_type_id": data["sup"], "label": "Сопровождение", "percent_of_norm": 5.0},
        {"work_type_id": data["org"], "label": "Орг. вопросы", "percent_of_norm": 10.0},
    ]
    bus.publish.assert_called_once_with(EVENT)


def test_list_by_team_includes_former_members_sorted(client, data):
    for emp, q in ((data["p"], 4), (data["p"], 1), (data["a"], 2), (data["left"], 3),
                   (data["stranger"], 1)):
        assert client.post(URL, json=_body(emp, quarter=q, involvement=0.5)).status_code == 201

    r = client.get(URL, params={"team": "ERP"})

    assert r.status_code == 200, r.text
    got = [(x["employee_name"], x["effective_quarter"]) for x in r.json()]
    assert got == [("Арбузов", 2), ("Бывший", 3), ("Пряничников", 1), ("Пряничников", 4)]


def test_custom_empty_and_by_role(client, data):
    empty = client.post(URL, json=_body(data["p"], normed={})).json()
    by_role = client.post(URL, json=_body(data["a"])).json()

    assert (empty["normed_custom"], empty["normed"], empty["involvement"]) == (True, [], None)
    assert (by_role["normed_custom"], by_role["normed"]) == (False, [])


def test_by_role_ignores_leftover_percents(client, data, testclient_db_session):
    body = _body(data["p"])
    body["normed"] = [{"work_type_id": data["org"], "percent_of_norm": 10}]

    r = client.post(URL, json=body)

    assert r.status_code == 201, r.text
    assert r.json()["normed"] == []
    assert testclient_db_session.query(EmployeePersonalNormed).count() == 0


def test_update_replaces_percents_and_publishes(client, bus, data, testclient_db_session):
    sid = client.post(URL, json=_body(data["p"], normed={data["org"]: 10, data["sup"]: 5})).json()["id"]
    bus.reset_mock()

    r = client.put(f"{URL}/{sid}", json=_body(data["p"], quarter=3, involvement=0.8,
                                              normed={data["org"]: 20}))

    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["effective_quarter"], body["involvement"]) == (3, 0.8)
    assert body["normed"] == [
        {"work_type_id": data["org"], "label": "Орг. вопросы", "percent_of_norm": 20.0},
    ]
    assert testclient_db_session.query(EmployeePersonalNormed).count() == 1
    bus.publish.assert_called_once_with(EVENT)


def test_delete_removes_percents_and_publishes(client, bus, data, testclient_db_session):
    sid = client.post(URL, json=_body(data["p"], normed={data["org"]: 10})).json()["id"]
    bus.reset_mock()

    r = client.delete(f"{URL}/{sid}")

    assert r.status_code == 204, r.text
    testclient_db_session.expire_all()
    assert testclient_db_session.query(EmployeePersonalSetting).count() == 0
    assert testclient_db_session.query(EmployeePersonalNormed).count() == 0
    bus.publish.assert_called_once_with(EVENT)


def test_missing_record_404(client, data):
    assert client.put(f"{URL}/nope", json=_body(data["p"])).status_code == 404
    assert client.delete(f"{URL}/nope").status_code == 404


def test_duplicate_employee_quarter_409(client, bus, data):
    assert client.post(URL, json=_body(data["p"], quarter=4)).status_code == 201
    sid = client.post(URL, json=_body(data["p"], quarter=3)).json()["id"]
    bus.reset_mock()

    r = client.post(URL, json=_body(data["p"], quarter=4))
    assert r.status_code == 409
    assert r.json()["detail"] == "Запись для этого сотрудника и квартала уже есть"

    r = client.put(f"{URL}/{sid}", json=_body(data["p"], quarter=4))
    assert r.status_code == 409
    bus.publish.assert_not_called()


@pytest.mark.parametrize("involvement", [-0.1, 1.5])
def test_involvement_out_of_range_422(client, bus, data, involvement):
    r = client.post(URL, json=_body(data["p"], involvement=involvement))

    assert r.status_code == 422
    assert r.json()["detail"] == "Вовлечённость — от 0 до 100%"
    bus.publish.assert_not_called()


def test_sum_over_100_422(client, data):
    r = client.post(URL, json=_body(data["p"], normed={data["org"]: 60, data["sup"]: 45}))

    assert r.status_code == 422
    assert r.json()["detail"] == "Сумма нормированных работ — 105%, больше 100%"


def test_percent_out_of_range_422(client, data):
    r = client.post(URL, json=_body(data["p"], normed={data["org"]: -5}))

    assert r.status_code == 422
    assert r.json()["detail"] == "Процент нормированной работы — от 0 до 100"


def test_work_type_not_reducing_pool_422(client, data):
    r = client.post(URL, json=_body(data["p"], normed={data["other"]: 5}))

    assert r.status_code == 422
    assert r.json()["detail"] == (
        "Вид работ «Прочие / Чужие» не уменьшает запас на проекты — "
        "его нельзя задать сотруднику"
    )


def test_unknown_work_type_or_employee_422(client, data):
    r = client.post(URL, json=_body(data["p"], normed={"nope": 5}))
    assert r.status_code == 422
    assert r.json()["detail"] == "Вид работ не найден"

    r = client.post(URL, json=_body("nope"))
    assert r.status_code == 422
    assert r.json()["detail"] == "Сотрудник не найден"


def test_duplicate_work_type_422(client, data):
    body = _body(data["p"], normed={data["org"]: 5})
    body["normed"].append({"work_type_id": data["org"], "percent_of_norm": 5})

    r = client.post(URL, json=body)

    assert r.status_code == 422
    assert r.json()["detail"] == "Вид работ указан дважды"


def test_work_type_used_in_personal_percents_cannot_be_deleted(client, data, testclient_db_session):
    client.post(URL, json=_body(data["p"], normed={data["org"]: 10}))

    r = client.delete(f"/api/v1/mandatory-work-types/{data['org']}")

    assert r.status_code == 409, r.text
    assert r.json()["detail"] == "Вид работ используется в личных нормированных работах сотрудников"
    testclient_db_session.expire_all()
    assert testclient_db_session.get(MandatoryWorkType, data["org"]) is not None
