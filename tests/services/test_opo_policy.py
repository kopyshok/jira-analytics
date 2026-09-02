"""Отсечка ОПЭ: с какого квартала этап не планируется."""
from app.models import AppSetting
from app.services import opo_policy


def _set_cutoff(db, value: str) -> None:
    db.add(AppSetting(key=opo_policy.SETTING_KEY, value=value))
    db.commit()


def test_no_setting_means_opo_stays_on(db_session):
    assert opo_policy.is_off(db_session, 2026, 4) is False


def test_quarter_before_cutoff_keeps_opo(db_session):
    _set_cutoff(db_session, "2026Q4")
    assert opo_policy.is_off(db_session, 2026, 3) is False
    assert opo_policy.is_off(db_session, 2025, 4) is False


def test_cutoff_quarter_and_later_drop_opo(db_session):
    _set_cutoff(db_session, "2026Q4")
    assert opo_policy.is_off(db_session, 2026, 4) is True
    assert opo_policy.is_off(db_session, 2027, 1) is True


def test_quarter_accepts_q_prefixed_string(db_session):
    _set_cutoff(db_session, "2026Q4")
    assert opo_policy.is_off(db_session, 2026, "Q4") is True
    assert opo_policy.is_off(db_session, 2026, "Q3") is False


def test_blank_setting_keeps_opo(db_session):
    _set_cutoff(db_session, "")
    assert opo_policy.is_off(db_session, 2030, 1) is False


def test_unknown_quarter_keeps_opo(db_session):
    _set_cutoff(db_session, "2026Q4")
    assert opo_policy.is_off(db_session, None, None) is False


def test_fold_moves_opo_hours_into_analyst_and_dev():
    folded = opo_policy.fold({"analyst": 10, "dev": 20, "qa": 5, "opo": 8}, 0.25)
    assert folded == {"analyst": 12.0, "dev": 26.0, "qa": 5.0, "opo": 0.0}


def test_fold_defaults_to_half_when_ratio_missing():
    folded = opo_policy.fold({"analyst": 0, "dev": 0, "qa": 0, "opo": 10}, None)
    assert folded["analyst"] == 5.0
    assert folded["dev"] == 5.0
    assert folded["opo"] == 0.0
