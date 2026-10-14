"""Препятствия к применению: свежесть отчёта, нерешённые пункты, копия базы, состояние."""
import json
from datetime import datetime, timedelta
from typing import Callable

from app.models import Employee, TeamDeskDailyRate
from app.services.jira_migration import store
from app.services.jira_migration.resolution import collect_blockers, resolve
from app.services.jira_migration.state import STATE_DONE, STATE_PENDING, set_migration_state
from tests.services.jira_migration.ready import seed_ready

NOW = datetime(2026, 10, 14, 12, 0)


def _blockers(db, backup=True, job=False):
    return collect_blockers(db, now=NOW, backup_confirmed=backup, job_running=job)


def _edit_report(db, change: Callable[[dict], None]) -> None:
    row = store.latest_report(db)
    report = store.report_data(row)
    change(report)
    row.report_json = json.dumps(report, ensure_ascii=False)
    db.commit()


def test_ready_state_has_no_blockers(db_session):
    seed_ready(db_session, NOW - timedelta(hours=1))

    assert _blockers(db_session) == []
    res = resolve(db_session)
    assert res.counts() == {"fields": 0, "issues": 0, "people": 0}
    assert res.deletable == ["OS-1"]
    assert [r["key"] for r in res.with_data] == ["OS-2", "OS-3"]
    assert res.issues_to_delete() == ["OS-1", "OS-2"]
    assert res.choices_dropped == 0
    assert res.offset_unexpected is False
    assert res.project_not_found == []


def test_backup_tick_job_and_finished_migration(db_session):
    seed_ready(db_session, NOW - timedelta(hours=1))

    assert _blockers(db_session, backup=False, job=True) == [
        "Идёт другая операция переезда — дождитесь её окончания",
        "Отметьте, что свежая копия базы сделана",
    ]
    set_migration_state(db_session, STATE_DONE)
    db_session.commit()
    assert _blockers(db_session) == ["Переезд уже выполнен"]


def test_no_report_and_failed_report(db_session):
    set_migration_state(db_session, STATE_PENDING)
    db_session.commit()
    assert _blockers(db_session) == ["Пробный прогон ещё не запускался"]

    report_id = store.start_report(db_session, NOW)
    store.fail_report(db_session, report_id, "сбой", NOW)
    assert _blockers(db_session) == [
        "Последний пробный прогон не завершился успешно — запустите его заново",
    ]


def test_running_dry_run_reports_only_the_running_job(db_session):
    set_migration_state(db_session, STATE_PENDING)
    db_session.commit()
    store.start_report(db_session, NOW)

    assert _blockers(db_session, job=True) == ["Идёт другая операция переезда — дождитесь её окончания"]
    # Прогон «идёт», но операции нет — сервис перезапускался посреди прогона.
    assert _blockers(db_session) == [
        "Последний пробный прогон не завершился успешно — запустите его заново",
    ]


def test_stale_report_blocks(db_session):
    seed_ready(db_session, NOW - timedelta(hours=25))
    assert _blockers(db_session) == ["Пробный прогон старше суток — запустите его заново"]


def test_essential_probe_failure_blocks(db_session):
    seed_ready(db_session, NOW - timedelta(hours=1))
    _edit_report(db_session, lambda r: r["probe"].extend([
        {"code": "search", "title": "Поиск задач", "essential": True, "ok": False, "detail": "400"},
        {"code": "statuses", "title": "Справочник статусов", "essential": False, "ok": False, "detail": ""},
    ]))

    assert _blockers(db_session) == [
        "Новая Jira не отвечала на обязательные запросы (Поиск задач) — запустите прогон заново",
    ]


def test_unresolved_issue_and_person_block(db_session):
    ids = seed_ready(db_session, NOW - timedelta(hours=1))
    store.set_decision(db_session, store.KIND_ISSUE, "OS-3", None, "Админ")
    store.set_decision(db_session, store.KIND_PERSON, ids["sidorov"], None, "Админ")

    assert _blockers(db_session) == [
        "Остались нерешённые пункты: поля — 0, задачи — 1, сотрудники — 1",
    ]


def test_unresolved_field_counts_until_decided(db_session):
    seed_ready(db_session, NOW - timedelta(hours=1))
    _edit_report(db_session, lambda r: r["fields"].append({
        "cloud_id": "customfield_12434", "cloud_name": "Пусконаладочные (ОПЭ) (ч)",
        "settings": ["jira_planned_opo_hours_field_id"], "labels": ["Плановые часы ОПЭ"],
        "suggested_id": None, "suggested_name": None, "auto_only": False,
    }))

    assert resolve(db_session).counts()["fields"] == 1
    store.set_decision(db_session, store.KIND_FIELD, "customfield_12434", {"dc_field_id": None}, "Админ")
    assert resolve(db_session).counts()["fields"] == 0


def test_failed_people_search_needs_decision(db_session):
    ids = seed_ready(db_session, NOW - timedelta(hours=1))
    store.set_decision(db_session, store.KIND_PERSON, ids["sidorov"], None, "Админ")

    def search_failed(report: dict) -> None:
        for row in report["people"]:
            if row["employee_id"] == ids["sidorov"]:
                row["status"] = "search_failed"

    _edit_report(db_session, search_failed)
    res = resolve(db_session)
    assert res.unresolved_people_ids() == [ids["sidorov"]]

    store.set_decision(db_session, store.KIND_PERSON, ids["sidorov"], {"action": "unbind"}, "Админ")
    assert resolve(db_session).counts()["people"] == 0


def test_employee_added_after_dry_run_blocks(db_session):
    seed_ready(db_session, NOW - timedelta(hours=1))
    db_session.add(Employee(jira_account_id="JIRAUSER99", display_name="Новенький"))
    db_session.commit()

    assert _blockers(db_session) == [
        "После пробного прогона появились новые сотрудники (1) — запустите прогон заново",
    ]


def test_issue_that_gained_service_data_needs_decision(db_session):
    ids = seed_ready(db_session, NOW - timedelta(hours=1))
    db_session.add(TeamDeskDailyRate(issue_id=ids["os1"], hours=1.0))
    db_session.commit()

    res = resolve(db_session)
    assert res.deletable == []
    assert res.counts()["issues"] == 1


def test_estimate_choice_on_unused_field_is_counted(db_session):
    seed_ready(db_session, NOW - timedelta(hours=1))
    # «Оценка 1С (ч)» — выбранная в споре оценка OS-91030 — больше не используется.
    store.set_decision(db_session, store.KIND_FIELD, "customfield_14648", {"dc_field_id": None}, "Админ")

    assert resolve(db_session).choices_dropped == 1


def test_report_warnings_pass_through(db_session):
    seed_ready(db_session, NOW - timedelta(hours=1))

    def warnings(report: dict) -> None:
        report["offset_unexpected"] = True
        report["issues"]["project_not_found"] = [{"key": "OLD", "issues": 12}]

    _edit_report(db_session, warnings)
    res = resolve(db_session)
    assert res.offset_unexpected is True
    assert res.project_not_found == [{"key": "OLD", "issues": 12}]
    assert _blockers(db_session) == []
