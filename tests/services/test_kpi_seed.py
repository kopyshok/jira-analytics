"""Первый запуск заводит шесть метрик и профиль «Аналитик» с суммой весов 1."""
import json

from app.models.kpi import KpiMetric, KpiProfile
from app.services.kpi.seed import seed_defaults


def test_seed_creates_six_metrics_and_profile(db_session):
    seed_defaults(db_session)
    db_session.commit()

    codes = {m.code for m in db_session.query(KpiMetric).all()}
    assert codes == {"quality", "deadlines", "regulations", "cycle_time",
                     "customer_score", "worklog_timeliness"}

    profile = db_session.query(KpiProfile).filter_by(code="analyst").one()
    assert round(sum(link.weight for link in profile.metrics), 6) == 1.0


def test_seed_is_idempotent(db_session):
    seed_defaults(db_session)
    db_session.commit()
    seed_defaults(db_session)
    db_session.commit()
    assert db_session.query(KpiMetric).count() == 6

    profile = db_session.query(KpiProfile).filter_by(code="analyst").one()
    assert len(profile.metrics) == 6


def _resolution_values(cond_json: str) -> set:
    conds = json.loads(cond_json)["conditions"]
    values: set = set()
    for c in conds:
        if c["attr"] == "resolution":
            values.update(c["value"])
    return values


def _issue_types(cond_json: str) -> set:
    conds = json.loads(cond_json)["conditions"]
    values: set = set()
    for c in conds:
        if c["attr"] == "issue_type":
            values.update(c["value"])
    return values


def test_seed_uses_actual_done_resolution_value(db_session):
    """Дефект 1: у этого арендатора резолюция называется Done, не «Готово» из ТЗ."""
    seed_defaults(db_session)
    db_session.commit()

    for metric in db_session.query(KpiMetric).all():
        for cond_json in (metric.numerator_json, metric.denominator_json):
            if not cond_json:
                continue
            values = _resolution_values(cond_json)
            assert "Готово" not in values
            if values:
                assert values == {"Done"}


def test_seed_deadlines_metric_scoped_to_epics_only(db_session):
    """Дефект 3: «Соблюдение сроков» оценивает квартальную цель — эпик, не ИТ-задачу."""
    seed_defaults(db_session)
    db_session.commit()

    deadlines = db_session.query(KpiMetric).filter_by(code="deadlines").one()
    assert _issue_types(deadlines.numerator_json) == {"Эпик"}
    assert _issue_types(deadlines.denominator_json) == {"Эпик"}


def test_seed_cycle_time_and_customer_score_keep_epic_or_it_task(db_session):
    """Остальные метрики не тронуты — заказчик уточнял только «Соблюдение сроков»."""
    seed_defaults(db_session)
    db_session.commit()

    cycle_time = db_session.query(KpiMetric).filter_by(code="cycle_time").one()
    customer_score = db_session.query(KpiMetric).filter_by(code="customer_score").one()
    assert _issue_types(cycle_time.numerator_json) == {"Эпик", "ИТ-задача"}
    assert _issue_types(customer_score.numerator_json) == {"Эпик", "ИТ-задача"}
