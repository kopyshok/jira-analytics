"""Выгрузка сценария отдаёт файл с именем сценария."""

import uuid
from urllib.parse import unquote

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app, settings
from app.models import PlanningScenario


def test_xlsx_and_pptx_named_after_scenario(testclient_db_session):
    db = testclient_db_session
    sc = PlanningScenario(
        id=str(uuid.uuid4()), name='Утверждённый: план "Q4"', quarter="Q4", year=2026, status="draft"
    )
    db.add(sc)
    db.commit()

    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    try:
        origin = settings.cors_origins[0]
        for ext in ("xlsx", "pptx"):
            resp = client.get(f"/api/v1/exports/scenarios/{sc.id}.{ext}", headers={"Origin": origin})
            assert resp.status_code == 200, resp.text
            cd = resp.headers["content-disposition"]
            utf8 = cd.split("filename*=UTF-8''", 1)[1]
            assert unquote(utf8) == f"Утверждённый_ план _Q4_.{ext}"
            # Браузер на другом порту сможет прочитать заголовок
            assert "content-disposition" in resp.headers.get("access-control-expose-headers", "").lower()
    finally:
        app.dependency_overrides.pop(get_db, None)
