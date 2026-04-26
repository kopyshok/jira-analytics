# tests/test_dashboard_endpoints.py
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_projects_widget_returns_200():
    resp = client.get("/api/v1/analytics/dashboard/projects?year=2026&quarter=2")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "done" in data
    assert "attention_list" in data
    assert "overrun_list" in data


def test_projects_widget_invalid_quarter():
    resp = client.get("/api/v1/analytics/dashboard/projects?year=2026&quarter=5")
    assert resp.status_code == 422
