"""Первый запуск заводит шесть метрик и профиль «Аналитик» с суммой весов 1."""
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
