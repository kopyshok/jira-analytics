"""Общие настройки KPI читаются с дефолтами и переопределяются из базы."""
from app.models.app_setting import AppSetting
from app.services.kpi.settings import read_kpi_settings


def test_defaults_when_db_empty(db_session):
    s = read_kpi_settings(db_session)
    assert s.excluded_statuses == ["Отменено"]
    assert s.worklog_deadline_days == 1
    assert s.worklog_deadline_time == "12:00"
    assert s.empty_policy == "redistribute"


def test_overrides_from_db(db_session):
    db_session.add(AppSetting(key="kpi_worklog_deadline_time", value="15:30"))
    db_session.add(AppSetting(key="kpi_excluded_statuses", value='["Отменено", "Отклонено"]'))
    db_session.commit()

    s = read_kpi_settings(db_session)
    assert s.worklog_deadline_time == "15:30"
    assert "Отклонено" in s.excluded_statuses
