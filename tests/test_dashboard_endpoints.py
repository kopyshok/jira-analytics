# tests/test_dashboard_endpoints.py
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_projects_widget_returns_200():
    resp = client.get("/api/v1/analytics/dashboard/projects?year=2026&quarter=2")
    assert resp.status_code == 200
    data = resp.json()
    # Counters
    assert "total" in data
    assert "done" in data
    assert "in_progress" in data
    assert "overdue" in data
    assert "not_started" in data
    # KPI top-level
    assert "total_fact_hours" in data
    assert "total_plan_hours" in data
    assert "avg_load_pct" in data
    assert "silent_count" in data
    assert "forecast_done" in data
    assert "forecast_pct" in data
    # Per-project list
    assert "projects" in data
    assert isinstance(data["projects"], list)
    # Удалённые поля больше НЕ должны быть в ответе
    assert "attention_list" not in data
    assert "overrun_list" not in data


def test_projects_widget_project_item_shape():
    """При наличии проектов в списке проверяем форму одного элемента."""
    resp = client.get("/api/v1/analytics/dashboard/projects?year=2026&quarter=2")
    data = resp.json()
    if data["projects"]:
        p = data["projects"][0]
        for key in [
            "issue_key", "title", "status_category",
            "plan_hours", "fact_hours", "delta_hours",
            "subtasks_done", "subtasks_total",
            "assignees", "assignees_total",
            "due_date", "days_to_due",
            "trend_hours_week", "trend_dir",
            "forecast_close_date", "forecast_in_quarter",
            "silent_days", "weekly_activity",
        ]:
            assert key in p, f"missing key: {key}"
        assert isinstance(p["assignees"], list)
        assert isinstance(p["weekly_activity"], list)
        assert p["trend_dir"] in ("up", "down", "flat")


def test_projects_widget_invalid_quarter():
    resp = client.get("/api/v1/analytics/dashboard/projects?year=2026&quarter=5")
    assert resp.status_code == 422


def test_norm_work_widget_returns_200():
    resp = client.get("/api/v1/analytics/dashboard/norm-work?year=2026&quarter=2")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total_plan" in data
    assert isinstance(data["items"], list)
    for item in data["items"]:
        assert "work_type_id" in item
        assert "plan_hours" in item
        assert "fact_hours" in item
        assert "pct" in item


def test_categories_widget_returns_200():
    resp = client.get("/api/v1/analytics/dashboard/categories?year=2026&quarter=2")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total_hours" in data
    for item in data["items"]:
        assert "key" in item
        assert "hours" in item
        assert "worklog_count" in item
        assert "employee_count" in item
        assert "avg_worklog_minutes" in item
        assert "pct" in item
