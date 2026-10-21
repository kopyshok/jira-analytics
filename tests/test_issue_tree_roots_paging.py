"""Очередь разбора листается страницами: сервер не отдаёт всю вкладку разом.

На рабочей базе в «К разбору» ~83 тыс. задач и ~32 тыс. верхних строк —
одним ответом это 33 МБ, браузер зависал на отрисовке. Теперь корни вкладки
приходят страницей, а отбор («Скрытые статусы», «Только переехавшие»),
сортировка и прыжок к задаче считаются на сервере по всей вкладке.
"""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import Issue, Project

ROOTS = "/api/v1/issues/tree/roots"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def make_project(db):
    created: list[str] = []

    def _make(key: str) -> Project:
        p = Project(id=f"proj-{key}", key=key, name=key, jira_project_id=f"j-{key}")
        db.add(p)
        db.flush()
        created.append(p.id)
        return p

    yield _make
    for pid in created:
        db.query(Issue).filter(Issue.project_id == pid).delete()
        db.query(Project).filter(Project.id == pid).delete()
    db.commit()


def _issue(db, proj, key, **overrides):
    """Задача «К разбору» по умолчанию: без категории и не подтверждена."""
    fields = dict(
        id=f"i-{key}", key=key, summary=key, issue_type="Task", status="Открыто",
        project_id=proj.id, jira_issue_id=f"j-{key}",
        assigned_category=None, category_verified=False, include_in_analysis=True,
    )
    fields.update(overrides)
    issue = Issue(**fields)
    db.add(issue)
    return issue


def _keys(resp) -> list[str]:
    assert resp.status_code == 200, resp.text
    return [n["key"] for n in resp.json()["items"]]


def test_roots_come_in_pages_with_full_total(client, db, make_project):
    p = make_project("PGN")
    for n in range(260):
        _issue(db, p, f"PGN-{n:04d}")
    db.commit()

    first = client.get(ROOTS, params={"project_keys": "PGN", "tab": "stack"})
    body = first.json()
    assert body["total"] == 260
    assert body["offset"] == 0
    assert len(body["items"]) == body["limit"] < 260

    pages = []
    for offset in (0, 100, 200):
        pages.append(_keys(client.get(ROOTS, params={
            "project_keys": "PGN", "tab": "stack", "offset": offset, "limit": 100,
        })))
    assert [len(p) for p in pages] == [100, 100, 60]
    flat = [k for page in pages for k in page]
    assert flat == sorted(f"PGN-{n:04d}" for n in range(260))


def test_roots_page_size_is_capped(client, make_project):
    resp = client.get(ROOTS, params={"tab": "stack", "project_keys": "ANY", "limit": 100000})
    assert resp.status_code == 422


def test_hidden_statuses_filtered_on_server_facet_lists_all(client, db, make_project):
    p = make_project("HST")
    _issue(db, p, "HST-1", status="Открыто")
    _issue(db, p, "HST-2", status="Отменено")
    _issue(db, p, "HST-3", status="Готово", issue_type="Epic")
    _issue(db, p, "HST-4", status="В работе", parent_id="i-HST-3")
    db.commit()

    resp = client.get(ROOTS, params={
        "project_keys": "HST", "tab": "stack", "hidden_statuses": "Отменено,Готово",
    })
    assert _keys(resp) == ["HST-1"]
    body = resp.json()
    assert body["total"] == 1
    # Список для «Скрытых статусов» — по всей очереди, включая скрытые и подзадачи.
    assert set(body["statuses"]) == {"Открыто", "Отменено", "Готово", "В работе"}


def test_only_moved_keeps_branches_with_moved_tasks_anywhere_below(client, db, make_project):
    p = make_project("MVD")
    # Эпик с категорией; переехавшая задача — на два уровня ниже, не раскрыта.
    _issue(db, p, "MVD-1", issue_type="Epic", assigned_category="dev", category_verified=True)
    _issue(db, p, "MVD-2", parent_id="i-MVD-1")
    _issue(db, p, "MVD-3", parent_id="i-MVD-2", parent_changed=True)
    _issue(db, p, "MVD-4", parent_id="i-MVD-1")
    # Обычная неразобранная задача без переездов — уходит из списка.
    _issue(db, p, "MVD-5")
    # Сама переехала (стала верхней).
    _issue(db, p, "MVD-6", parent_changed=True)
    db.commit()

    params = {"project_keys": "MVD", "tab": "stack", "only_moved": "true"}
    resp = client.get(ROOTS, params=params)
    assert _keys(resp) == ["MVD-1", "MVD-6"]
    assert resp.json()["total"] == 2

    # Внутри ветки — только путь к переехавшей задаче.
    kids = client.get("/api/v1/issues/i-MVD-1/children", params=params)
    assert kids.status_code == 200, kids.text
    assert [n["key"] for n in kids.json()] == ["MVD-2"]
    grand = client.get("/api/v1/issues/i-MVD-2/children", params=params)
    assert [n["key"] for n in grand.json()] == ["MVD-3"]

    # Без переключателя — как раньше, все ветки.
    assert _keys(client.get(ROOTS, params={"project_keys": "MVD", "tab": "stack"})) == [
        "MVD-1", "MVD-5", "MVD-6",
    ]
    all_kids = client.get("/api/v1/issues/i-MVD-1/children", params={"project_keys": "MVD", "tab": "stack"})
    assert [n["key"] for n in all_kids.json()] == ["MVD-2", "MVD-4"]


def test_sort_by_status_change_and_goals_across_pages(client, db, make_project):
    p = make_project("SRT")
    _issue(db, p, "SRT-1", status_changed_at=datetime(2026, 3, 1), goals="Б")
    _issue(db, p, "SRT-2", status_changed_at=None, goals=None)
    _issue(db, p, "SRT-3", status_changed_at=datetime(2025, 1, 1), goals="а")
    _issue(db, p, "SRT-4", status_changed_at=datetime(2026, 9, 1), goals="В")
    db.commit()

    def keys(sort, offset=0, limit=100):
        return _keys(client.get(ROOTS, params={
            "project_keys": "SRT", "tab": "stack", "sort": sort, "offset": offset, "limit": limit,
        }))

    assert keys("status_changed_at") == ["SRT-2", "SRT-3", "SRT-1", "SRT-4"]
    assert keys("-status_changed_at") == ["SRT-4", "SRT-1", "SRT-3", "SRT-2"]
    # Порядок сквозной: вторая страница продолжает первую.
    assert keys("-status_changed_at", offset=2, limit=2) == ["SRT-3", "SRT-2"]
    assert keys("goals") == ["SRT-2", "SRT-3", "SRT-1", "SRT-4"]
    assert keys("-goals") == ["SRT-4", "SRT-1", "SRT-3", "SRT-2"]
    bad = client.get(ROOTS, params={"project_keys": "SRT", "tab": "stack", "sort": "summary; drop"})
    assert bad.status_code == 422


def test_focus_returns_page_with_branch_of_found_issue(client, db, make_project):
    p = make_project("FCS")
    for n in range(250):
        _issue(db, p, f"FCS-{n:04d}", issue_type="Epic" if n == 230 else "Task")
    _issue(db, p, "FCS-9000", parent_id="i-FCS-0230")
    _issue(db, p, "FCS-9001", parent_id="i-FCS-9000")
    db.commit()

    resp = client.get(ROOTS, params={
        "project_keys": "FCS", "tab": "stack", "limit": 100, "focus_id": "i-FCS-9001",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["focus_found"] is True
    assert body["offset"] == 200
    assert "FCS-0230" in [n["key"] for n in body["items"]]

    # Задачи нет в этой очереди — страница не меняется.
    miss = client.get(ROOTS, params={
        "project_keys": "FCS", "tab": "active", "limit": 100, "offset": 0, "focus_id": "i-FCS-9001",
    }).json()
    assert miss["focus_found"] is False
    assert miss["offset"] == 0
