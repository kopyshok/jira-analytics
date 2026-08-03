"""Миграция возвращает сроки, Cycle Time и оценку заказчика на исполнителя.

Решение заказчика поверх ``k12a``. Метрики, заведённые руководителем вручную
(``is_builtin=False``), миграция не трогает.
"""
import importlib.util
import json
from pathlib import Path

from app.models.kpi import KpiMetric


def _load_migration_module():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "k14a_kpi_person_assignee.py"
    spec = importlib.util.spec_from_file_location("migration_k14a_kpi_person_assignee", path)
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


def _conditions(person: str) -> str:
    return json.dumps({
        "unit": "issues", "person_field": person, "period_window": "closed_in",
        "conditions": [{"attr": "issue_type", "op": "in", "value": ["Эпик"]}],
    }, ensure_ascii=False)


def _person(cond_json: str) -> str:
    return json.loads(cond_json)["person_field"]


def _seed_after_k12a(db):
    """Состояние базы после ``k12a``: встроенные метрики считаются по автору."""
    db.add_all([
        KpiMetric(
            code="quality", name="Качество выпуска", calc_kind="ratio", is_builtin=True,
            numerator_json=_conditions("linked_issue_author"),
            denominator_json=_conditions("author"),
        ),
        KpiMetric(
            code="deadlines", name="Соблюдение сроков", calc_kind="ratio", is_builtin=True,
            description="Доля задач автора, выполненных не позже плановой даты окончания",
            numerator_json=_conditions("author"), denominator_json=_conditions("author"),
        ),
        KpiMetric(
            code="regulations", name="Соблюдение регламентов", calc_kind="ratio", is_builtin=True,
            numerator_json=_conditions("author"), denominator_json=_conditions("author"),
        ),
        KpiMetric(
            code="cycle_time", name="Cycle Time", calc_kind="norm_to_fact", is_builtin=True,
            numerator_json=_conditions("author"), denominator_json=None,
        ),
        KpiMetric(
            code="customer_score", name="Оценка заказчика", calc_kind="score_to_max",
            is_builtin=True, numerator_json=_conditions("author"), denominator_json=None,
        ),
        KpiMetric(
            code="custom", name="Метрика руководителя", calc_kind="ratio", is_builtin=False,
            numerator_json=_conditions("author"), denominator_json=_conditions("author"),
        ),
    ])
    db.commit()


def test_migration_switches_three_metrics_to_assignee(db_session):
    _seed_after_k12a(db_session)

    module = _load_migration_module()
    module.op = _RealBindOp(db_session.connection())
    module.upgrade()
    db_session.commit()

    by_code = {m.code: m for m in db_session.query(KpiMetric).all()}
    assert _person(by_code["deadlines"].numerator_json) == "assignee"
    assert _person(by_code["deadlines"].denominator_json) == "assignee"
    assert _person(by_code["cycle_time"].numerator_json) == "assignee"
    assert _person(by_code["customer_score"].numerator_json) == "assignee"
    assert "исполнителя" in by_code["deadlines"].description
    # Качество выпуска и регламенты остаются по автору — их заказчик не трогал.
    assert _person(by_code["quality"].numerator_json) == "linked_issue_author"
    assert _person(by_code["quality"].denominator_json) == "author"
    assert _person(by_code["regulations"].numerator_json) == "author"
    # Метрика руководителя — не встроенная, миграция её не трогает.
    assert _person(by_code["custom"].numerator_json) == "author"


def test_migration_is_idempotent(db_session):
    _seed_after_k12a(db_session)

    module = _load_migration_module()
    module.op = _RealBindOp(db_session.connection())
    module.upgrade()
    db_session.commit()
    module.op = _RealBindOp(db_session.connection())
    module.upgrade()
    db_session.commit()

    by_code = {m.code: m for m in db_session.query(KpiMetric).all()}
    assert _person(by_code["cycle_time"].numerator_json) == "assignee"
