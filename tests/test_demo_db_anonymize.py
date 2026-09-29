"""Обезличивание демо-базы (scripts/demo_db): словарь соответствий, ключи задач, секреты, проверка утечек."""
from __future__ import annotations

import json
import sqlite3

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401  — регистрирует все таблицы в Base.metadata
from app.database import Base
from app.models import (
    AppSetting,
    BacklogItem,
    Comment,
    Employee,
    EmployeeTeam,
    Issue,
    IssueLink,
    PlanningScenario,
    Project,
    Team,
    User,
    UserRole,
)
from scripts.demo_db import leak_check
from scripts.demo_db.anonymize import Sensitive, anonymize, surname_forms

PRIMARY = "Команда 1С (ERP - Товарный учет)"
OTHER = "Команда Х"
NAME_1 = "Шестопалов Аркадий Викторович"
NAME_2 = "Мирошниченко Зинаида"
ACC_1 = "712020:3c98c49a-297a-4c44-b0ad-000000000001"
ACC_2 = "5e7365b5b715180c47c16ba5"
EMAIL_1 = "shestopalov_a_v@itgri.ru"
SUMMARY_1 = "Доработать отчёт для Мирошниченко по складу Ломбард"


@pytest.fixture
def conn(tmp_path):
    path = tmp_path / "src.db"
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add_all([Team(name=PRIMARY), Team(name=OTHER)])
        e1 = Employee(jira_account_id=ACC_1, display_name=NAME_1, email=EMAIL_1,
                      avatar_url="https://secure.gravatar.com/avatar/abc")
        e2 = Employee(jira_account_id=ACC_2, display_name=NAME_2,
                      email="miroshnichenko_z@itgri.ru")
        s.add_all([e1, e2])
        s.flush()
        s.add_all([
            EmployeeTeam(employee_id=e1.id, team=PRIMARY, is_primary=True),
            EmployeeTeam(employee_id=e2.id, team=OTHER, is_primary=True),
            EmployeeTeam(employee_id=e2.id, team=PRIMARY, is_primary=False),
        ])
        user = User(email=EMAIL_1, password_hash="$2b$12$realhash", display_name="Шестопалов Аркадий",
                    role=UserRole.manager)
        user.selected_teams = [PRIMARY, OTHER]  # хранится с \uXXXX-экранированием
        s.add(user)
        project = Project(jira_project_id="10001", key="ERPTU", name="ERP Товарный учёт")
        s.add(project)
        s.flush()
        i1 = Issue(jira_issue_id="20001", key="ERPTU-1", summary=SUMMARY_1,
                   description="Секретное описание от Шестопалова", issue_type="Задача",
                   status="В работе", project_id=project.id,
                   assignee_display_name=NAME_1, assignee_account_id=ACC_1,
                   reporter_display_name=NAME_2, reporter_account_id=ACC_2,
                   team=PRIMARY, participating_teams=json.dumps([OTHER, PRIMARY], ensure_ascii=False))
        i2 = Issue(jira_issue_id="20002", key="ERPTU-2", summary="Настройка обмена с банком Ломбард",
                   issue_type="Баг", status="Готово", project_id=project.id,
                   team=OTHER, participating_teams="[]", category_context_key="ERPTU-1")
        s.add_all([i1, i2])
        s.flush()
        s.add_all([
            IssueLink(source_issue_id=i1.id, target_issue_id=i2.id, link_type="Blocks"),
            BacklogItem(title=SUMMARY_1, issue_id=i1.id, project_id=project.id,
                        customer="Бородулина Эльвира", team=PRIMARY),
            PlanningScenario(name=f"2026 Q4 {PRIMARY}", quarter="Q4", year=2026, team=PRIMARY),
            Comment(jira_comment_id="c-1", body="Коммент от Шестопалова", issue_id=i1.id,
                    author_id=e1.id),
            AppSetting(key="jira_api_token", value="ATATT3xFfGF0-secret"),
            AppSetting(key="jira_email", value=EMAIL_1),
            AppSetting(key="jira_base_url", value="https://itgri.atlassian.net"),
        ])
        s.commit()
    engine.dispose()
    connection = sqlite3.connect(path)
    yield connection
    connection.close()


def _one(conn, sql, *args):
    return conn.execute(sql, args).fetchone()[0]


def test_anonymize_maps_consistently_and_clears_text(conn):
    sensitive = anonymize(conn, primary_team=PRIMARY)

    # Одно ФИО → одно вымышленное во всех таблицах.
    fake_1 = _one(conn, "SELECT assignee_display_name FROM issues WHERE key = 'PRA-1'")
    assert fake_1 and fake_1 != NAME_1
    assert _one(conn, "SELECT count(*) FROM employees WHERE display_name = ?", fake_1) == 1
    fake_2 = _one(conn, "SELECT reporter_display_name FROM issues WHERE key = 'PRA-1'")
    assert fake_2 and fake_2 not in (NAME_2, fake_1)
    assert _one(conn, "SELECT count(*) FROM employees WHERE display_name = ?", fake_2) == 1
    assert _one(conn, "SELECT display_name FROM users") == fake_1  # тот же человек без отчества

    # Учётки, e-mail, аватары.
    acc_1 = _one(conn, "SELECT jira_account_id FROM employees WHERE display_name = ?", fake_1)
    assert acc_1.startswith("acc-")
    assert _one(conn, "SELECT assignee_account_id FROM issues WHERE key = 'PRA-1'") == acc_1
    email_1 = _one(conn, "SELECT email FROM employees WHERE display_name = ?", fake_1)
    assert email_1.startswith("user") and email_1.endswith("@example.com")
    assert _one(conn, "SELECT email FROM users") == email_1
    assert _one(conn, "SELECT count(*) FROM employees WHERE avatar_url IS NOT NULL") == 0

    # Команды: одинаково во всех местах, включая JSON; основная → «Команда Альфа».
    fake_other = _one(conn, "SELECT team FROM issues WHERE key = 'PRA-2'")
    assert fake_other.startswith("Команда ") and fake_other not in (OTHER, "Команда Альфа")
    assert {r[0] for r in conn.execute("SELECT name FROM teams")} == {"Команда Альфа", fake_other}
    assert {r[0] for r in conn.execute("SELECT team FROM employee_teams")} == {"Команда Альфа", fake_other}
    assert _one(conn, "SELECT team FROM issues WHERE key = 'PRA-1'") == "Команда Альфа"
    assert json.loads(_one(conn, "SELECT selected_teams FROM users")) == ["Команда Альфа", fake_other]
    assert json.loads(_one(conn, "SELECT participating_teams FROM issues WHERE key = 'PRA-1'")) == [
        fake_other, "Команда Альфа"]
    assert _one(conn, "SELECT team FROM planning_scenarios") == "Команда Альфа"
    assert PRIMARY not in _one(conn, "SELECT name FROM planning_scenarios")

    # Ключи и проекты.
    assert {r[0] for r in conn.execute("SELECT key FROM issues")} == {"PRA-1", "PRA-2"}
    assert _one(conn, "SELECT key FROM projects") == "PRA"
    assert _one(conn, "SELECT name FROM projects") == "Проект А"
    assert _one(conn, "SELECT category_context_key FROM issues WHERE key = 'PRA-2'") == "PRA-1"

    # Названия заменены, свободный текст пуст, бэклог — как у задачи.
    summary_1 = _one(conn, "SELECT summary FROM issues WHERE key = 'PRA-1'")
    assert summary_1 and summary_1 != SUMMARY_1
    assert _one(conn, "SELECT title FROM backlog_items") == summary_1
    assert not _one(conn, "SELECT description FROM issues WHERE key = 'PRA-1'")
    assert not _one(conn, "SELECT body FROM comments")
    assert _one(conn, "SELECT customer FROM backlog_items").startswith("Заказчик ")

    # Секреты и адрес Jira.
    assert not _one(conn, "SELECT value FROM app_settings WHERE key = 'jira_api_token'")
    assert not _one(conn, "SELECT value FROM app_settings WHERE key = 'jira_email'")
    assert _one(conn, "SELECT value FROM app_settings WHERE key = 'jira_base_url'") == "https://jira.example.com"
    assert _one(conn, "SELECT password_hash FROM users") != "$2b$12$realhash"

    assert leak_check.check(conn, sensitive) == []


@pytest.mark.parametrize("table, column, planted", [
    ("issues", "summary", "Отчёт Шестопалову"),
    ("users", "selected_teams", json.dumps([OTHER])),  # \uXXXX-экранирование
    ("worklogs", "comment_text", "пишите на boss@itgri.ru"),
    ("issues", "description", "см. ERPTU-1 и https://itgri.atlassian.net"),
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
