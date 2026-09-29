"""Обезличивание демо-базы (scripts/demo_db): словарь соответствий, ключи задач, секреты, проверка утечек.

Все имена, домены и команды здесь вымышленные.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401  — регистрирует все таблицы в Base.metadata
from app.database import Base
from app.models import (
    Absence,
    AbsenceReason,
    AppSetting,
    BacklogItem,
    Comment,
    Employee,
    EmployeeTeam,
    Issue,
    IssueLink,
    PlanningScenario,
    Project,
    ScenarioAbsenceSnapshot,
    ScenarioRevision,
    SyncSchedule,
    Team,
    User,
    UserRole,
)
from scripts.demo_db import build_demo_db, leak_check
from scripts.demo_db.anonymize import Sensitive, anonymize, surname_forms
from scripts.demo_db.fake_data import key_offset

PRIMARY = "Команда Склад-Сервис"
OTHER = "Команда Х"
NAME_1 = "Шестопалов Аркадий Викторович"
NAME_2 = "Мирошниченко Зинаида"
ACC_1 = "712020:3c98c49a-297a-4c44-b0ad-000000000001"
ACC_2 = "5e7365b5b715180c47c16ba5"
DOMAIN = "acme-demo.ru"
EMAIL_1 = f"shestopalov_a_v@{DOMAIN}"
SUMMARY_1 = "Доработать отчёт для Мирошниченко по складу Северный"
SUMMARY_2 = "Настройка обмена с банком Северный"
OFFSET = key_offset("PRA")
KEY_1, KEY_2, KEY_3 = (f"PRA-{n + OFFSET}" for n in (1, 2, 3))
STATUS = "Проработка требований"


@pytest.fixture
def src_path(tmp_path):
    path = tmp_path / "src.db"
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add_all([Team(name=PRIMARY), Team(name=OTHER)])
        e1 = Employee(jira_account_id=ACC_1, display_name=NAME_1, email=EMAIL_1,
                      avatar_url="https://secure.gravatar.com/avatar/abc")
        e2 = Employee(jira_account_id=ACC_2, display_name=NAME_2, email=f"miroshnichenko_z@{DOMAIN}")
        vacation = AbsenceReason(code="vacation", label="Отпуск", is_planned=True)
        sick = AbsenceReason(code="sick", label="Больничный")
        s.add_all([e1, e2, vacation, sick])
        s.flush()
        s.add_all([
            EmployeeTeam(employee_id=e1.id, team=PRIMARY, is_primary=True),
            EmployeeTeam(employee_id=e2.id, team=OTHER, is_primary=True),
            EmployeeTeam(employee_id=e2.id, team=PRIMARY, is_primary=False),
            Absence(employee_id=e1.id, reason_id=vacation.id, start_date=date(2026, 7, 1), end_date=date(2026, 7, 14)),
            Absence(employee_id=e1.id, reason_id=sick.id, start_date=date(2026, 8, 3), end_date=date(2026, 8, 5)),
        ])
        user = User(email=EMAIL_1, password_hash="$2b$12$realhash", display_name="Шестопалов Аркадий",
                    role=UserRole.manager)
        user.selected_teams = [PRIMARY, OTHER]  # хранится с \uXXXX-экранированием
        s.add(user)
        project = Project(jira_project_id="10001", key="WHS", name="Склад и логистика")
        s.add(project)
        s.flush()
        i1 = Issue(jira_issue_id="20001", key="WHS-1", summary=SUMMARY_1,
                   description="Секретное описание от Шестопалова", issue_type="Задача",
                   status="В работе", project_id=project.id, environment="PROD",
                   assignee_display_name=NAME_1, assignee_account_id=ACC_1,
                   reporter_display_name=NAME_2, reporter_account_id=ACC_2,
                   team=PRIMARY, participating_teams=json.dumps([OTHER, PRIMARY], ensure_ascii=False))
        i2 = Issue(jira_issue_id="20002", key="WHS-2", summary=SUMMARY_2, environment="стенд склада 2",
                   issue_type="Баг", status="Готово", project_id=project.id,
                   team=OTHER, participating_teams="[]", category_context_key="WHS-1")
        # Название задачи совпадает со статусом: статус — справочное значение, это не утечка.
        i3 = Issue(jira_issue_id="20003", key="WHS-3", summary=STATUS, status=STATUS, issue_type="Задача",
                   project_id=project.id, team=OTHER, participating_teams="[]")
        scenario = PlanningScenario(name=f"2026 Q4 {PRIMARY}", quarter="Q4", year=2026, team=PRIMARY)
        s.add_all([i1, i2, i3, scenario])
        s.flush()
        revision = ScenarioRevision(scenario_id=scenario.id, revision_number=1, approved_at=datetime(2026, 9, 1))
        s.add(revision)
        s.flush()
        s.add_all([
            IssueLink(source_issue_id=i1.id, target_issue_id=i2.id, link_type="Blocks"),
            BacklogItem(title=SUMMARY_1, issue_id=i1.id, project_id=project.id,
                        customer="Бородулина Эльвира", team=PRIMARY),
            Comment(jira_comment_id="c-1", body="Коммент от Шестопалова", issue_id=i1.id,
                    author_id=e1.id),
            ScenarioAbsenceSnapshot(revision_id=revision.id, employee_id=e1.id, employee_name=NAME_1,
                                    start_date=date(2026, 7, 1), end_date=date(2026, 7, 14), hours_total=80,
                                    reason_id=vacation.id, reason_label="Отпуск"),
            ScenarioAbsenceSnapshot(revision_id=revision.id, employee_id=e1.id, employee_name=NAME_1,
                                    start_date=date(2026, 8, 3), end_date=date(2026, 8, 5), hours_total=24,
                                    reason_id=None, reason_label="Больничный"),
            SyncSchedule(name="daily_incremental", cron_expr="*/20 * * * *", mode="normal", enabled=True),
            AppSetting(key="jira_api_token", value="ATATT3xFfGF0-secret"),
            AppSetting(key="jira_email", value=EMAIL_1),
            AppSetting(key="jira_base_url", value="https://acme-demo.atlassian.net"),
            AppSetting(key="jira_team_field_id", value="customfield_10001"),
            AppSetting(key="ui_teams_categories", value=PRIMARY),
            AppSetting(key="llm_gemini_model", value="gemini-demo-flash"),
            AppSetting(key="llm_gemini_api_key", value="AIza-secret"),
            AppSetting(key="llm_omniroute_base_url", value="http://10.1.2.3:20128/v1"),
            AppSetting(key="some_future_setting", value="что-то новое"),
        ])
        s.commit()
    engine.dispose()
    return path


@pytest.fixture
def conn(src_path):
    connection = sqlite3.connect(src_path)
    yield connection
    connection.close()


def _one(conn, sql, *args):
    return conn.execute(sql, args).fetchone()[0]


def _setting(conn, key):
    return _one(conn, "SELECT value FROM app_settings WHERE key = ?", key)


def test_anonymize_maps_consistently_and_clears_text(conn):
    sensitive = anonymize(conn, primary_team=PRIMARY)

    # Одно ФИО → одно вымышленное во всех таблицах.
    fake_1 = _one(conn, "SELECT assignee_display_name FROM issues WHERE key = ?", KEY_1)
    assert fake_1 and fake_1 != NAME_1
    assert _one(conn, "SELECT count(*) FROM employees WHERE display_name = ?", fake_1) == 1
    fake_2 = _one(conn, "SELECT reporter_display_name FROM issues WHERE key = ?", KEY_1)
    assert fake_2 and fake_2 not in (NAME_2, fake_1)
    assert _one(conn, "SELECT count(*) FROM employees WHERE display_name = ?", fake_2) == 1
    assert _one(conn, "SELECT display_name FROM users") == fake_1  # тот же человек без отчества

    # Учётки, e-mail, аватары.
    acc_1 = _one(conn, "SELECT jira_account_id FROM employees WHERE display_name = ?", fake_1)
    assert acc_1.startswith("acc-")
    assert _one(conn, "SELECT assignee_account_id FROM issues WHERE key = ?", KEY_1) == acc_1
    email_1 = _one(conn, "SELECT email FROM employees WHERE display_name = ?", fake_1)
    assert email_1.startswith("user") and email_1.endswith("@example.com")
    assert _one(conn, "SELECT email FROM users") == email_1
    assert _one(conn, "SELECT count(*) FROM employees WHERE avatar_url IS NOT NULL") == 0

    # Команды: одинаково во всех местах, включая JSON; основная → «Команда Альфа».
    fake_other = _one(conn, "SELECT team FROM issues WHERE key = ?", KEY_2)
    assert fake_other.startswith("Команда ") and fake_other not in (OTHER, "Команда Альфа")
    assert sensitive.primary_team == "Команда Альфа"
    assert {r[0] for r in conn.execute("SELECT name FROM teams")} == {"Команда Альфа", fake_other}
    assert {r[0] for r in conn.execute("SELECT team FROM employee_teams")} == {"Команда Альфа", fake_other}
    assert _one(conn, "SELECT team FROM issues WHERE key = ?", KEY_1) == "Команда Альфа"
    assert json.loads(_one(conn, "SELECT selected_teams FROM users")) == ["Команда Альфа", fake_other]
    assert json.loads(_one(conn, "SELECT participating_teams FROM issues WHERE key = ?", KEY_1)) == [
        fake_other, "Команда Альфа"]
    assert _one(conn, "SELECT team FROM planning_scenarios") == "Команда Альфа"
    assert PRIMARY not in _one(conn, "SELECT name FROM planning_scenarios")

    # Ключи: буквы вымышленные, номера сдвинуты на число проекта — везде одинаково.
    assert 10_000 <= OFFSET <= 40_000
    assert {r[0] for r in conn.execute("SELECT key FROM issues")} == {KEY_1, KEY_2, KEY_3}
    assert _one(conn, "SELECT key FROM projects") == "PRA"
    assert _one(conn, "SELECT name FROM projects") == "Проект А"
    assert _one(conn, "SELECT category_context_key FROM issues WHERE key = ?", KEY_2) == KEY_1

    # Названия заменены, свободный текст пуст, бэклог — как у задачи; окружение — только стандартное.
    summary_1 = _one(conn, "SELECT summary FROM issues WHERE key = ?", KEY_1)
    assert summary_1 and summary_1 != SUMMARY_1
    assert _one(conn, "SELECT title FROM backlog_items") == summary_1
    assert not _one(conn, "SELECT description FROM issues WHERE key = ?", KEY_1)
    assert not _one(conn, "SELECT body FROM comments")
    assert _one(conn, "SELECT customer FROM backlog_items").startswith("Заказчик ")
    assert _one(conn, "SELECT summary FROM issues WHERE key = ?", KEY_3) != STATUS
    assert _one(conn, "SELECT status FROM issues WHERE key = ?", KEY_3) == STATUS
    assert _one(conn, "SELECT environment FROM issues WHERE key = ?", KEY_1) == "PROD"
    assert not _one(conn, "SELECT environment FROM issues WHERE key = ?", KEY_2)

    # Настройки: белый список, остальное пусто; адрес Jira — демо.
    assert _setting(conn, "jira_base_url") == "https://jira.example.com"
    assert _setting(conn, "jira_team_field_id") == "customfield_10001"
    assert _setting(conn, "llm_gemini_model") == "gemini-demo-flash"
    assert _setting(conn, "ui_teams_categories") == "Команда Альфа"
    for key in ("jira_api_token", "jira_email", "llm_gemini_api_key", "llm_omniroute_base_url",
                "some_future_setting"):
        assert _setting(conn, key) == "", key
    assert _one(conn, "SELECT password_hash FROM users") != "$2b$12$realhash"

    # Больничные удалены (и в снимках сценариев), отпуск остался; расписания синхронизации выключены.
    assert _one(conn, "SELECT count(*) FROM absences") == 1
    assert _one(conn, "SELECT count(*) FROM absences a JOIN absence_reasons r ON r.id = a.reason_id "
                      "WHERE r.code = 'sick'") == 0
    assert [r[0] for r in conn.execute("SELECT reason_label FROM scenario_absence_snapshots")] == ["Отпуск"]
    assert _one(conn, "SELECT count(*) FROM sync_schedule WHERE enabled = 1") == 0

    assert leak_check.check(conn, sensitive) == []


def test_primary_team_must_exist(conn):
    with pytest.raises(ValueError, match="Команда Несуществующая"):
        anonymize(conn, primary_team="Команда Несуществующая")


def test_unclassified_text_column_fails(conn):
    """Новая текстовая колонка без политики обезличивания — сборка падает, а не пропускает её."""
    conn.execute("ALTER TABLE issues ADD COLUMN reviewer_note TEXT")

    with pytest.raises(RuntimeError, match=r"issues\.reviewer_note"):
        anonymize(conn, primary_team=PRIMARY)


@pytest.mark.parametrize("table, column, planted", [
    ("issues", "summary", "Отчёт Шестопалову"),
    ("users", "selected_teams", json.dumps([OTHER])),  # \uXXXX-экранирование
    ("worklogs", "comment_text", f"пишите на boss@{DOMAIN}"),
    ("issues", "description", "см. WHS-1 и https://acme-demo.atlassian.net"),
    ("issues", "description", "репозиторий https://git.internal.local/core"),
    ("issues", "description", "база на моноблоке 10.28.20.40, проверить"),
    ("issues", "summary", f"  {SUMMARY_2.upper()}  "),  # дословная копия исходного названия
])
def test_leak_check_finds_planted_leak(conn, table, column, planted):
    sensitive = anonymize(conn, primary_team=PRIMARY)
    if table == "worklogs":
        conn.execute("INSERT INTO worklogs (id, jira_worklog_id, issue_id, employee_id, started_at, hours, "
                     "time_spent_seconds, created_at, updated_at) "
                     "SELECT 'w1', 'w1', i.id, e.id, '2026-01-01', 1, 3600, '2026-01-01', '2026-01-01' "
                     "FROM issues i, employees e LIMIT 1")
    conn.execute(f"UPDATE {table} SET {column} = ?", (planted,))

    findings = leak_check.check(conn, sensitive)

    assert findings
    assert all(f.startswith(f"{table}.{column}: ") for f in findings)


def test_leak_check_scans_binary_values():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE blobs (id TEXT, data BLOB)")
    conn.execute("INSERT INTO blobs VALUES ('1', ?)", ("выгрузка: https://files.acme-demo.ru/x".encode(),))

    assert leak_check.check(conn, Sensitive(strings=frozenset(), project_keys=frozenset())) == [
        "blobs.data: выгрузка: https://files.acme-demo.ru/x"]


def test_surname_is_matched_as_word_in_any_case_form():
    """Фамилия ищется словом во всех падежах, а не подстрокой внутри обычных слов."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE notes (id TEXT, body TEXT)")
    conn.executemany("INSERT INTO notes VALUES (?, ?)", [
        ("1", "из черновиков сценария"),
        ("2", "боковая панель, боковое меню"),
        ("3", "передать Новикову"),
    ])
    sensitive = Sensitive(strings=frozenset(), project_keys=frozenset(),
                          words=frozenset(surname_forms("новиков") | surname_forms("боков")))

    assert leak_check.check(conn, sensitive) == ["notes.body: передать новикову"]


# --- сборка целиком: временный файл, отказ от перезаписи ---------------------------------------


def _build(src_path, out, *extra):
    return build_demo_db.main(["--source", str(src_path), "--out", str(out), "--primary-team", PRIMARY, *extra])


def _leftovers(out):
    return [p.name for p in out.parent.iterdir() if p.name.startswith(out.name)]


def test_build_removes_partial_copy_on_error(src_path, tmp_path, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("сбой обезличивания")

    monkeypatch.setattr(build_demo_db, "anonymize", boom)
    out = tmp_path / "out" / "demo.db"

    with pytest.raises(RuntimeError, match="сбой обезличивания"):
        _build(src_path, out)

    assert _leftovers(out) == []


def test_build_removes_copy_when_leak_found(src_path, tmp_path, monkeypatch):
    monkeypatch.setattr(build_demo_db.leak_check, "check", lambda *_a: ["issues.summary: утечка"])
    out = tmp_path / "demo.db"

    assert _build(src_path, out) == 1
    assert _leftovers(out) == []


def test_build_writes_demo_db_and_refuses_to_overwrite(src_path, tmp_path):
    out = tmp_path / "demo.db"

    assert _build(src_path, out) == 0
    assert _leftovers(out) == ["demo.db"]
    db = sqlite3.connect(out)
    try:
        assert db.execute("SELECT default_team FROM users WHERE email = 'demo@example.com'").fetchone() == (
            "Команда Альфа",)
        assert db.execute("PRAGMA journal_mode").fetchone() == ("delete",)
    finally:
        db.close()
    size = out.stat().st_size

    assert _build(src_path, out) == 1  # без --force существующий файл не трогаем
    assert out.stat().st_size == size
    assert _build(src_path, out, "--force") == 0


@pytest.mark.parametrize("target", ["same", "jira_analytics.db"])
def test_build_refuses_dangerous_out(src_path, tmp_path, target):
    out = src_path if target == "same" else tmp_path / "x" / "jira_analytics.db"

    assert _build(src_path, out, "--force") == 1
    assert not (tmp_path / "x").exists()
