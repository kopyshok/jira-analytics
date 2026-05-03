"""ScenarioAllocation manual sort_order behavior:
- toggle False→True bumps row to top (min - 1.0)
- toggle True→False does NOT change sort_order (sticky)
- reorder endpoint rewrites positions atomically
- new BacklogItem auto-allocated to bottom of every draft scenario
"""


import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


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


def _override(db):
    app.dependency_overrides[get_db] = lambda: db


def _seed_three_items(db):
    from app.models import BacklogItem

    db.add_all([
        BacklogItem(id="b1", title="Alpha", priority=1),
        BacklogItem(id="b2", title="Bravo", priority=2),
        BacklogItem(id="b3", title="Charlie", priority=3),
    ])
    db.commit()


def _create_scenario(client) -> str:
    r = client.post(
        "/api/v1/planning/scenarios",
        json={"name": "Q2", "year": 2026, "quarter": 2},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _ids_in_order(client, scenario_id):
    r = client.get(f"/api/v1/planning/scenarios/{scenario_id}/allocations")
    assert r.status_code == 200, r.text
    return [a["backlog_item_id"] for a in r.json()], [a["id"] for a in r.json()]


def test_toggle_on_moves_row_to_top(db_session):
    _seed_three_items(db_session)
    _override(db_session)
    try:
        client = TestClient(app)
        sid = _create_scenario(client)
        items_before, alloc_ids_before = _ids_in_order(client, sid)
        assert items_before == ["b1", "b2", "b3"]

        # Toggle middle item ON.
        target_alloc = alloc_ids_before[1]  # b2
        r = client.patch(
            f"/api/v1/planning/scenarios/{sid}/allocations/{target_alloc}",
            json={"included": True},
        )
        assert r.status_code == 200, r.text

        items_after, _ = _ids_in_order(client, sid)
        assert items_after == ["b2", "b1", "b3"], items_after
    finally:
        app.dependency_overrides.clear()


def test_toggle_off_keeps_position(db_session):
    _seed_three_items(db_session)
    _override(db_session)
    try:
        client = TestClient(app)
        sid = _create_scenario(client)
        _, alloc_ids = _ids_in_order(client, sid)

        # Включаем все по очереди — каждая едет в верх.
        for aid in alloc_ids:
            client.patch(
                f"/api/v1/planning/scenarios/{sid}/allocations/{aid}",
                json={"included": True},
            )
        items_after_on, alloc_ids_after_on = _ids_in_order(client, sid)
        # b3, b2, b1 — каждое следующее включение перебивало предыдущее.
        assert items_after_on == ["b3", "b2", "b1"]

        # Снимаем галочку с b2 (середина) — позиция должна СОХРАНИТЬСЯ.
        b2_alloc = alloc_ids_after_on[1]
        r = client.patch(
            f"/api/v1/planning/scenarios/{sid}/allocations/{b2_alloc}",
            json={"included": False},
        )
        assert r.status_code == 200

        items_after_off, _ = _ids_in_order(client, sid)
        assert items_after_off == ["b3", "b2", "b1"], items_after_off

        # И снимаем с верхней (b3) — тоже без перестановки.
        b3_alloc = alloc_ids_after_on[0]
        client.patch(
            f"/api/v1/planning/scenarios/{sid}/allocations/{b3_alloc}",
            json={"included": False},
        )
        items_final, _ = _ids_in_order(client, sid)
        assert items_final == ["b3", "b2", "b1"], items_final
    finally:
        app.dependency_overrides.clear()


def test_reorder_endpoint_rewrites_positions(db_session):
    _seed_three_items(db_session)
    _override(db_session)
    try:
        client = TestClient(app)
        sid = _create_scenario(client)
        _, alloc_ids = _ids_in_order(client, sid)

        # Reverse the order via reorder endpoint.
        new_order = list(reversed(alloc_ids))
        r = client.patch(
            f"/api/v1/planning/scenarios/{sid}/allocations/reorder",
            json={"ordered_ids": new_order},
        )
        assert r.status_code == 200, r.text

        items_after, _ = _ids_in_order(client, sid)
        assert items_after == ["b3", "b2", "b1"], items_after
    finally:
        app.dependency_overrides.clear()


def test_reorder_partial_keeps_unmentioned_at_bottom(db_session):
    _seed_three_items(db_session)
    _override(db_session)
    try:
        client = TestClient(app)
        sid = _create_scenario(client)
        _, alloc_ids = _ids_in_order(client, sid)

        # Указали только b3 — остальные в конец, в исходном порядке.
        b3_alloc = alloc_ids[2]
        r = client.patch(
            f"/api/v1/planning/scenarios/{sid}/allocations/reorder",
            json={"ordered_ids": [b3_alloc]},
        )
        assert r.status_code == 200, r.text

        items_after, _ = _ids_in_order(client, sid)
        assert items_after == ["b3", "b1", "b2"], items_after
    finally:
        app.dependency_overrides.clear()


def test_sync_backlog_appends_new_to_bottom(db_session):
    from app.models import BacklogItem

    _seed_three_items(db_session)
    _override(db_session)
    try:
        client = TestClient(app)
        sid = _create_scenario(client)
        items_before, _ = _ids_in_order(client, sid)
        assert items_before == ["b1", "b2", "b3"]

        # Добавили новый BacklogItem; синкаем сценарий.
        db_session.add(BacklogItem(id="b4", title="Delta", priority=None))
        db_session.commit()

        r = client.post(f"/api/v1/planning/scenarios/{sid}/sync-backlog")
        assert r.status_code == 200, r.text

        items_after, _ = _ids_in_order(client, sid)
        assert items_after == ["b1", "b2", "b3", "b4"], items_after
    finally:
        app.dependency_overrides.clear()


def test_reorder_blocked_for_approved_scenario(db_session):
    from app.models import PlanningScenario

    _seed_three_items(db_session)
    _override(db_session)
    try:
        client = TestClient(app)
        sid = _create_scenario(client)
        _, alloc_ids = _ids_in_order(client, sid)

        # Approve: фиксируем сценарий.
        scenario = db_session.get(PlanningScenario, sid)
        scenario.status = "approved"
        db_session.commit()

        r = client.patch(
            f"/api/v1/planning/scenarios/{sid}/allocations/reorder",
            json={"ordered_ids": list(reversed(alloc_ids))},
        )
        assert r.status_code == 409
    finally:
        app.dependency_overrides.clear()
