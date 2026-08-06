"""Дефекты 1 и 3: миграция чинит резолюцию и сужает «Соблюдение сроков» до эпиков
на уже заведённых справочниках, не трогая метрики руководителя.

Справочники существующих (уже развёрнутых) баз заведены СТАРЫМ ``seed.py`` —
резолюция «Готово», в «Соблюдение сроков» ещё входит «ИТ-задача». Текущий
``seed_defaults()`` уже содержит оба исправления (задачи 1 и 3), поэтому
здесь легаси-данные заводятся вручную — так тест воспроизводит реальную
уже установленную базу, а не то, что завела бы сегодняшняя (уже
исправленная) версия кода.
"""
import importlib.util
import json
from pathlib import Path


def _load_migration_module():
    repo_root = Path(__file__).resolve().parents[1]
    path = repo_root / "alembic" / "versions" / "k10a_kpi_fix_resolution_and_deadlines_scope.py"
    spec = importlib.util.spec_from_file_location(
        "migration_k10a_kpi_fix_resolution_and_deadlines_scope", path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _RealBindOp:
    """Прокси op.get_bind() на реальное соединение тестовой БД."""

    def __init__(self, connection):
        self._connection = connection

    def get_bind(self):
        return self._connection


def _conditions_of(cond_json: str) -> list[dict]:
    return json.loads(cond_json)["conditions"]


def _legacy_builtin_metrics(db):
    """Четыре встроенные метрики, как их заводил старый ``seed.py`` — резолюция
    «Готово», «Соблюдение сроков» ещё принимает «ИТ-задачу» наравне с «Эпиком»."""
    from app.models.kpi import KpiMetric

    quality = KpiMetric(
        code="quality", name="Качество выпуска", calc_kind="ratio",
        invert=True, cap_at_100=True, is_builtin=True,
        numerator_json=json.dumps({
            "unit": "issues", "person_field": "linked_issue_author", "period_window": "closed_in",
            "conditions": [
                {"attr": "issue_type", "op": "in", "value": ["Баг"]},
                {"attr": "resolution", "op": "in", "value": ["Готово"]},
                {"attr": "environment", "op": "eq", "value": "PROD"},
            ],
        }, ensure_ascii=False),
        denominator_json=json.dumps({
            "unit": "issues", "person_field": "author", "period_window": "closed_in",
            "conditions": [
                {"attr": "issue_type", "op": "in", "value": ["Задача", "Баг"]},
                {"attr": "resolution", "op": "in", "value": ["Готово"]},
            ],
        }, ensure_ascii=False),
    )
    deadlines = KpiMetric(
        code="deadlines", name="Соблюдение сроков", calc_kind="ratio",
        invert=False, cap_at_100=True, is_builtin=True,
        numerator_json=json.dumps({
            "unit": "issues", "person_field": "assignee", "period_window": "closed_in",
            "conditions": [
                {"attr": "issue_type", "op": "in", "value": ["Эпик", "ИТ-задача"]},
                {"attr": "resolution", "op": "in", "value": ["Готово"]},
                {"attr": "resolved_on_time", "op": "is_true", "value": None},
            ],
        }, ensure_ascii=False),
        denominator_json=json.dumps({
            "unit": "issues", "person_field": "assignee", "period_window": "closed_in",
            "conditions": [
                {"attr": "issue_type", "op": "in", "value": ["Эпик", "ИТ-задача"]},
                {"attr": "resolution", "op": "in", "value": ["Готово"]},
            ],
        }, ensure_ascii=False),
    )
    cycle_time = KpiMetric(
        code="cycle_time", name="Cycle Time", calc_kind="norm_to_fact",
        invert=False, cap_at_100=True, is_builtin=True, fact_field="cycle_time_fact",
        numerator_json=json.dumps({
            "unit": "issues", "person_field": "assignee", "period_window": "closed_in",
            "conditions": [
                {"attr": "issue_type", "op": "in", "value": ["Эпик", "ИТ-задача"]},
                {"attr": "resolution", "op": "in", "value": ["Готово"]},
            ],
        }, ensure_ascii=False),
    )
    custom = KpiMetric(
        code="custom", name="Своя метрика руководителя", calc_kind="ratio",
        invert=False, cap_at_100=True, is_builtin=False,
        numerator_json=json.dumps({
            "unit": "issues", "person_field": "author", "period_window": "closed_in",
            "conditions": [
                {"attr": "resolution", "op": "in", "value": ["Готово"]},
                {"attr": "issue_type", "op": "in", "value": ["Эпик", "ИТ-задача"]},
            ],
        }, ensure_ascii=False),
        denominator_json=json.dumps({
            "unit": "issues", "person_field": "author", "period_window": "closed_in",
            "conditions": [],
        }, ensure_ascii=False),
    )
    db.add_all([quality, deadlines, cycle_time, custom])
    db.commit()
    return {"quality": quality, "deadlines": deadlines, "cycle_time": cycle_time, "custom": custom}


def test_upgrade_fixes_resolution_and_narrows_deadlines_to_epics(db_session):
    metrics = _legacy_builtin_metrics(db_session)

    module = _load_migration_module()
    module.op = _RealBindOp(db_session.connection())
    module.upgrade()
    db_session.commit()

    from app.models.kpi import KpiMetric

    for metric in db_session.query(KpiMetric).filter_by(is_builtin=True).all():
        for cond_json in (metric.numerator_json, metric.denominator_json):
            if not cond_json:
                continue
            for cond in _conditions_of(cond_json):
                if cond["attr"] == "resolution":
                    assert cond["value"] == ["Done"]

    db_session.refresh(metrics["deadlines"])
    for cond_json in (metrics["deadlines"].numerator_json, metrics["deadlines"].denominator_json):
        for cond in _conditions_of(cond_json):
            if cond["attr"] == "issue_type":
                assert cond["value"] == ["Эпик"]

    # cycle_time заказчик не просил трогать — тип задачи остаётся прежним.
    db_session.refresh(metrics["cycle_time"])
    for cond in _conditions_of(metrics["cycle_time"].numerator_json):
        if cond["attr"] == "issue_type":
            assert cond["value"] == ["Эпик", "ИТ-задача"]


def test_upgrade_is_idempotent(db_session):
    _legacy_builtin_metrics(db_session)

    module = _load_migration_module()
    module.op = _RealBindOp(db_session.connection())
    module.upgrade()
    db_session.commit()

    from app.models.kpi import KpiMetric

    before = {
        m.id: (m.numerator_json, m.denominator_json)
        for m in db_session.query(KpiMetric).all()
    }

    # commit() выше отдаёт соединение обратно в пул — берём заново.
    module.op = _RealBindOp(db_session.connection())
    module.upgrade()
    db_session.commit()

    after = {
        m.id: (m.numerator_json, m.denominator_json)
        for m in db_session.query(KpiMetric).all()
    }
    assert before == after


def test_upgrade_is_a_noop_on_already_fixed_data(db_session):
    """Свежая база: ``seed_defaults()`` уже содержит оба исправления — миграция
    не имеет права испортить корректные данные, приняв их за легаси."""
    from app.services.kpi.seed import seed_defaults

    seed_defaults(db_session)
    db_session.commit()

    from app.models.kpi import KpiMetric

    before = {
        m.id: (m.numerator_json, m.denominator_json)
        for m in db_session.query(KpiMetric).all()
    }

    module = _load_migration_module()
    module.op = _RealBindOp(db_session.connection())
    module.upgrade()
    db_session.commit()

    after = {
        m.id: (m.numerator_json, m.denominator_json)
        for m in db_session.query(KpiMetric).all()
    }
    assert before == after


def test_upgrade_does_not_touch_manually_created_metric(db_session):
    """Метрика руководителя со своим значением резолюции — не трогаем даже если
    оно совпадает по написанию с исправляемым."""
    metrics = _legacy_builtin_metrics(db_session)
    custom = metrics["custom"]
    original_numerator = custom.numerator_json

    module = _load_migration_module()
    module.op = _RealBindOp(db_session.connection())
    module.upgrade()
    db_session.commit()

    db_session.refresh(custom)
    assert custom.numerator_json == original_numerator


def test_downgrade_restores_original_values(db_session):
    _legacy_builtin_metrics(db_session)

    from app.models.kpi import KpiMetric

    original = {
        m.id: (m.numerator_json, m.denominator_json)
        for m in db_session.query(KpiMetric).all()
    }

    module = _load_migration_module()
    module.op = _RealBindOp(db_session.connection())
    module.upgrade()
    db_session.commit()
    # commit() выше отдаёт соединение обратно в пул — берём заново.
    module.op = _RealBindOp(db_session.connection())
    module.downgrade()
    db_session.commit()

    restored = {
        m.id: (m.numerator_json, m.denominator_json)
        for m in db_session.query(KpiMetric).all()
    }
    assert restored == original
