"""ВАЖНО 8 ревью Фазы 3: откат сида метрик KPI не стирает данные, заведённые руководителем."""
import importlib.util
from pathlib import Path

from sqlalchemy import text


def _load_migration_module():
    repo_root = Path(__file__).resolve().parents[1]
    path = repo_root / "alembic" / "versions" / "k07a_kpi_seed_defaults.py"
    spec = importlib.util.spec_from_file_location("migration_k07a_kpi_seed_defaults", path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _RealBindOp:
    """Прокси op.execute на реальное соединение тестовой БД — проверяем SQL по-настоящему,
    а не факт вызова метода на моке."""

    def __init__(self, connection):
        self._connection = connection

    def execute(self, statement) -> None:
        self._connection.execute(text(statement))


def test_downgrade_keeps_manually_created_profile_and_metric(db_session):
    """Раньше `DELETE FROM kpi_profile_metrics` без условия стирал веса ЛЮБЫХ
    профилей — в том числе заведённых руководителем после сида, если они
    ссылались хоть на одну встроенную метрику. Теперь удаление ограничено
    профилем 'analyst' и встроенными метриками."""
    from app.services.kpi.seed import seed_defaults

    seed_defaults(db_session)
    db_session.commit()

    from app.models.kpi import KpiMetric, KpiProfile, KpiProfileMetric

    custom_metric = KpiMetric(
        code="custom", name="Своя метрика", calc_kind="ratio", invert=False, cap_at_100=True,
        is_builtin=False,
        numerator_json='{"unit": "issues", "person_field": "author", "period_window": "closed_in", "conditions": []}',
        denominator_json='{"unit": "issues", "person_field": "author", "period_window": "closed_in", "conditions": []}',
    )
    custom_profile = KpiProfile(code="custom_profile", name="Свой профиль",
                                is_enabled=True, target_pct=80.0)
    db_session.add_all([custom_metric, custom_profile])
    db_session.commit()
    db_session.add(KpiProfileMetric(
        profile_id=custom_profile.id, metric_id=custom_metric.id, weight=1.0,
    ))
    db_session.commit()

    module = _load_migration_module()
    module.op = _RealBindOp(db_session.connection())

    module.downgrade()
    db_session.commit()

    # Встроенный сид удалён.
    assert db_session.query(KpiProfile).filter_by(code="analyst").first() is None
    assert db_session.query(KpiMetric).filter_by(is_builtin=True).count() == 0

    # Профиль и метрика руководителя — целы, вес не потерян.
    remaining_profile = db_session.query(KpiProfile).filter_by(code="custom_profile").one()
    assert db_session.query(KpiMetric).filter_by(code="custom").first() is not None
    assert len(remaining_profile.metrics) == 1
    assert remaining_profile.metrics[0].weight == 1.0
