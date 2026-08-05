"""Настройки рабочего стола тимлида: группы статусов, пороги, типы задач."""
from app.services.team_desk.config import (
    group_of_status,
    load_config,
    save_config,
)


def test_defaults_when_nothing_saved(db_session):
    cfg = load_config(db_session)
    assert cfg.thresholds["decomposition_hours"] == 16
    assert cfg.thresholds["overrun_pct"] == 30
    assert cfg.thresholds["stale_days"] == 5
    assert "В РАБОТЕ" in cfg.status_groups["dev"]
    assert "ФИЧА-РЕВЬЮ" in cfg.status_groups["waiting"]
    assert cfg.queue_statuses == ["К выполнению", "В РАБОТЕ", "Ожидает помещения"]
    assert "Подзадача" in cfg.subtask_types
    assert cfg.assignee_types == ["Research"]


def test_save_and_reload(db_session):
    cfg = load_config(db_session)
    cfg.thresholds["decomposition_hours"] = 24
    cfg.status_groups["dev"].append("НОВЫЙ СТАТУС")
    save_config(db_session, cfg)

    reloaded = load_config(db_session)
    assert reloaded.thresholds["decomposition_hours"] == 24
    assert "НОВЫЙ СТАТУС" in reloaded.status_groups["dev"]


def test_unknown_status_falls_into_unassigned(db_session):
    cfg = load_config(db_session)
    assert group_of_status(cfg, "В РАБОТЕ") == "dev"
    assert group_of_status(cfg, "Тестирование") == "waiting"
    assert group_of_status(cfg, "Backlog") == "todo"
    assert group_of_status(cfg, "ГОТОВО") == "done"
    assert group_of_status(cfg, "Совершенно новый статус") == "unassigned"
    assert group_of_status(cfg, None) == "unassigned"


def test_broken_stored_value_falls_back_to_defaults(db_session):
    from app.models import AppSetting
    from app.services.team_desk.config import SETTING_KEY

    db_session.add(AppSetting(key=SETTING_KEY, value="не json"))
    db_session.commit()

    cfg = load_config(db_session)
    assert cfg.thresholds["decomposition_hours"] == 16
