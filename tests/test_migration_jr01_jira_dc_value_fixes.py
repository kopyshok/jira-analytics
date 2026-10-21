"""Миграция jr01: настройки после переезда на Jira DC — новые имена статусов, резолюции, поля QA."""
import importlib.util
import json
from pathlib import Path

from app.models.app_setting import AppSetting
from app.models.kpi import KpiMetric
from app.models.sync_state import SyncState


def _module():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "jr01_jira_dc_value_fixes.py"
    spec = importlib.util.spec_from_file_location("migration_jr01", path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _spec(*conditions):
    return {"unit": "issues", "person_field": "author", "period_window": "closed_in",
            "conditions": list(conditions)}


def test_metric_spec_done_and_backlog():
    m = _module()
    spec = _spec(
        {"attr": "resolution", "op": "in", "value": ["Done"]},
        {"attr": "status", "op": "not_in", "value": ["Backlog", "Бэклог"]},
        {"attr": "issue_type", "op": "in", "value": ["Done"]},
    )
    assert m.fix_metric_spec(spec) is True
    assert spec["conditions"][0]["value"] == ["Готово"]
    assert spec["conditions"][1]["value"] == ["Backlog", "Бэклог", "IDEA BACKLOG", "APPROVED IDEA BACKLOG"]
    assert spec["conditions"][2]["value"] == ["Done"]  # не резолюция — не трогаем
    assert m.fix_metric_spec(spec) is False  # повторно — без изменений


def test_metric_spec_eq_and_dedupe():
    m = _module()
    spec = _spec({"attr": "resolution", "op": "eq", "value": "Done"},
                 {"attr": "resolution", "op": "in", "value": ["Done", "Готово"]})
    assert m.fix_metric_spec(spec) is True
    assert spec["conditions"][0]["value"] == "Готово"
    assert spec["conditions"][1]["value"] == ["Готово"]


def test_status_list_additions_only_next_to_source():
    m = _module()
    assert m.fix_status_list(["ГОТОВО", "Отменено"]) == ["ГОТОВО", "Отменено", "Won't Do"]
    assert m.fix_status_list(["К выполнению", "В РАБОТЕ"]) == ["К выполнению", "В РАБОТЕ", "Сделать"]
    assert m.fix_status_list(["Backlog"]) == ["Backlog", "IDEA BACKLOG", "APPROVED IDEA BACKLOG"]
    assert m.fix_status_list(["Приостановлено"]) == ["Приостановлено", "Hold"]
    assert m.fix_status_list(["В РАБОТЕ"]) == ["В РАБОТЕ"]
    assert m.fix_status_list(["Отменено", "Won't Do"]) == ["Отменено", "Won't Do"]


def test_qa_setting():
    m = _module()
    raw = json.dumps([
        {"field_id": "customfield_11140", "kind": "alt", "name": "Тестирование (ч)"},
        {"field_id": "customfield_10845", "kind": "alt", "name": "QA spent (ч)"},
    ], ensure_ascii=False)
    fixed = json.loads(m.fix_qa_setting(raw))
    assert fixed[1] == {"field_id": "customfield_11042", "kind": "alt", "name": "Оценка QA (ч)"}
    assert fixed[0]["field_id"] == "customfield_11140"
    assert m.fix_qa_setting("customfield_10845") == "customfield_11042"
    assert m.fix_qa_setting("customfield_11140") == "customfield_11140"
    assert m.fix_qa_setting("") == ""


def test_upgrade_on_database(db_session):
    m = _module()
    metric = KpiMetric(
        code="quality", name="Качество", calc_kind="ratio", invert=False, cap_at_100=True,
        is_builtin=True,
        numerator_json=json.dumps(_spec({"attr": "resolution", "op": "in", "value": ["Done"]})),
        denominator_json=json.dumps(_spec({"attr": "status", "op": "not_in", "value": ["Backlog"]})),
    )
    db_session.add_all([
        metric,
        AppSetting(key="kpi_excluded_statuses", value=json.dumps(["Отменено"], ensure_ascii=False)),
        AppSetting(key="team_desk_config", value=json.dumps({
            "status_groups": {"todo": ["Backlog", "К выполнению"], "done": ["ГОТОВО", "Отменено"]},
            "queue_statuses": ["К выполнению", "В РАБОТЕ"],
            "hidden_statuses": ["Backlog"],
            "thresholds": {"wip_limit": 3},
        }, ensure_ascii=False)),
        AppSetting(key="jira_planned_qa_hours_field_id", value=json.dumps(
            [{"field_id": "customfield_10845", "kind": "alt", "name": "QA spent (ч)"}],
            ensure_ascii=False)),
    ])
    db_session.commit()

    for _ in range(2):  # второй прогон ничего не меняет
        m._upgrade(db_session.connection())
        db_session.commit()

    db_session.expire_all()
    got = db_session.get(KpiMetric, metric.id)
    assert json.loads(got.numerator_json)["conditions"][0]["value"] == ["Готово"]
    assert json.loads(got.denominator_json)["conditions"][0]["value"] == [
        "Backlog", "IDEA BACKLOG", "APPROVED IDEA BACKLOG"]
    settings = {s.key: s.value for s in db_session.query(AppSetting)}
    assert json.loads(settings["kpi_excluded_statuses"]) == ["Отменено", "Won't Do"]
    desk = json.loads(settings["team_desk_config"])
    # Добавки идут в порядке источников: Отменено, К выполнению, Backlog, Приостановлено.
    assert desk["status_groups"]["todo"] == [
        "Backlog", "К выполнению", "Сделать", "IDEA BACKLOG", "APPROVED IDEA BACKLOG"]
    assert desk["status_groups"]["done"] == ["ГОТОВО", "Отменено", "Won't Do"]
    assert desk["queue_statuses"] == ["К выполнению", "В РАБОТЕ", "Сделать"]
    assert desk["hidden_statuses"] == ["Backlog", "IDEA BACKLOG", "APPROVED IDEA BACKLOG"]
    assert desk["thresholds"] == {"wip_limit": 3}
    assert json.loads(settings["jira_planned_qa_hours_field_id"])[0]["field_id"] == "customfield_11042"


def test_upgrade_on_empty_database(db_session):
    """Новая установка: настроек нет — миграция ничего не создаёт и не падает."""
    m = _module()
    m._upgrade(db_session.connection())
    db_session.commit()
    assert db_session.query(AppSetting).count() == 0


def test_qa_setting_stricter():
    m = _module()
    # пробелы в идентификаторе не мешают
    spaced = json.dumps([{"field_id": " customfield_10845 ", "name": "QA spent (ч)"}])
    assert json.loads(m.fix_qa_setting(spaced)) == [
        {"field_id": "customfield_11042", "name": "Оценка QA (ч)"}]
    # поле с другим названием администратор переименовал сам — не трогаем
    other = json.dumps([{"field_id": "customfield_10845", "name": "Моё поле"}], ensure_ascii=False)
    assert m.fix_qa_setting(other) == other
    # «Оценка QA» уже есть — старое поле убираем, дубля нет
    both = json.dumps([
        {"field_id": "customfield_10845", "name": "QA spent (ч)"},
        {"field_id": "customfield_11042", "name": "Оценка QA (ч)"},
    ], ensure_ascii=False)
    assert json.loads(m.fix_qa_setting(both)) == [{"field_id": "customfield_11042", "name": "Оценка QA (ч)"}]


def test_desk_additions_respect_admin_grouping():
    m = _module()
    cfg = {"status_groups": {
        "todo": ["К выполнению"],
        "waiting": ["Сделать"],  # администратор сам положил «Сделать» в другую группу
        "done": ["Отменено"],
    }}
    assert m.fix_desk_config(cfg) is True
    assert cfg["status_groups"]["todo"] == ["К выполнению"]
    assert cfg["status_groups"]["waiting"] == ["Сделать"]
    assert cfg["status_groups"]["done"] == ["Отменено", "Won't Do"]


def test_upgrade_resets_issue_and_pause_cursors(db_session):
    from datetime import datetime

    m = _module()
    stamp = datetime(2026, 10, 1, 12, 0)
    db_session.add_all([
        SyncState(entity_name="issues", scope="", last_success_at=stamp),
        SyncState(entity_name="issues", scope="Team X", last_success_at=stamp),
        SyncState(entity_name="paused_days", scope="", last_success_at=stamp),
        SyncState(entity_name="worklogs", scope="", last_success_at=stamp),
    ])
    db_session.commit()

    m._upgrade(db_session.connection())
    db_session.commit()

    db_session.expire_all()
    got = {(s.entity_name, s.scope): s.last_success_at for s in db_session.query(SyncState)}
    assert got[("issues", "")] is None
    assert got[("issues", "Team X")] is None
    assert got[("paused_days", "")] is None
    assert got[("worklogs", "")] == stamp
