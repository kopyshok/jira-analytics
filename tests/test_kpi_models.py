"""Справочники KPI: метрика, профиль, вес, норматив, утверждение."""
import json

from app.models.kpi import KpiMetric, KpiProfile, KpiProfileMetric, KpiCycleTimeNorm


def test_metric_and_profile(db_session):
    metric = KpiMetric(
        code="quality",
        name="Качество выпуска",
        description="Обратная доля багов на проде",
        calc_kind="ratio",
        numerator_json=json.dumps({"unit": "issues", "person_field": "linked_issue_author",
                                   "period_window": "closed_in", "conditions": []}),
        denominator_json=json.dumps({"unit": "issues", "person_field": "author",
                                     "period_window": "closed_in", "conditions": []}),
        invert=True,
        cap_at_100=True,
    )
    profile = KpiProfile(code="analyst", name="Аналитик", role_code="analyst", target_pct=80.0)
    db_session.add_all([metric, profile])
    db_session.commit()

    db_session.add(KpiProfileMetric(profile_id=profile.id, metric_id=metric.id, weight=0.2))
    db_session.add(KpiCycleTimeNorm(team="Платежи", year=2026, quarter=3, norm_value=70.0))
    db_session.commit()

    loaded = db_session.query(KpiProfile).filter_by(code="analyst").one()
    assert loaded.target_pct == 80.0
    assert len(loaded.metrics) == 1
    assert loaded.metrics[0].weight == 0.2
