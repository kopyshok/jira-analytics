"""Миграция переводит встроенные метрики на автора задачи и не трогает чужие.

Развёрнутая база могла быть подправлена руками через справочник (у «Качества
выпуска» признак был переставлен на исполнителя), поэтому легаси-строки здесь
заводятся вручную, а не сегодняшним ``seed_defaults()``.
"""
import importlib.util
import json
from pathlib import Path

from app.models.kpi import KpiMetric


def _load_migration_module():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "k12a_kpi_person_is_author.py"
    spec = importlib.util.spec_from_file_location("migration_k12a_kpi_person_is_author", path)
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


def _conditions(unit_person: str, **extra) -> str:
    return json.dumps({
        "unit": "issues", "person_field": unit_person, "period_window": "closed_in",
        "conditions": [{"attr": "issue_type", "op": "in", "value": ["Эпик"]}],
        **extra,
    }, ensure_ascii=False)


def _person(cond_json: str) -> str:
    return json.loads(cond_json)["person_field"]


def _seed_legacy(db):
    db.add_all([
        KpiMetric(
            code="quality", name="Качество выпуска", calc_kind="ratio", is_builtin=True,
            numerator_json=_conditions("assignee"), denominator_json=_conditions("assignee"),
        ),
        KpiMetric(
            code="deadlines", name="Соблюдение сроков", calc_kind="ratio", is_builtin=True,
            description="Доля задач исполнителя, выполненных не позже плановой даты окончания",
            numerator_json=_conditions("assignee"), denominator_json=_conditions("assignee"),
        ),
        KpiMetric(
            code="cycle_time", name="Cycle Time", calc_kind="norm_to_fact", is_builtin=True,
            numerator_json=_conditions("assignee"), denominator_json=None,
        ),
        KpiMetric(
            code="custom", name="Метрика руководителя", calc_kind="ratio", is_builtin=False,
            numerator_json=_conditions("assignee"), denominator_json=_conditions("assignee"),
        ),
    ])
    db.commit()


def test_migration_switches_builtin_metrics_to_author(db_session):
    _seed_legacy(db_session)

    module = _load_migration_module()
    # commit() выше отдаёт соединение обратно в пул — берём заново.
    module.op = _RealBindOp(db_session.connection())
    module.upgrade()
    db_session.commit()

    by_code = {m.code: m for m in db_session.query(KpiMetric).all()}
    assert _person(by_code["quality"].numerator_json) == "linked_issue_author"
    assert _person(by_code["quality"].denominator_json) == "author"
    assert _person(by_code["deadlines"].numerator_json) == "author"
    assert _person(by_code["deadlines"].denominator_json) == "author"
    assert _person(by_code["cycle_time"].numerator_json) == "author"
    assert "автора" in by_code["deadlines"].description
    # Метрика руководителя — не встроенная, миграция её не трогает.
    assert _person(by_code["custom"].numerator_json) == "assignee"


def test_migration_downgrade_returns_assignee(db_session):
    _seed_legacy(db_session)

    module = _load_migration_module()
    module.op = _RealBindOp(db_session.connection())
    module.upgrade()
    db_session.commit()

    module.op = _RealBindOp(db_session.connection())
    module.downgrade()
    db_session.commit()

    by_code = {m.code: m for m in db_session.query(KpiMetric).all()}
    assert _person(by_code["deadlines"].numerator_json) == "assignee"
    assert _person(by_code["cycle_time"].numerator_json) == "assignee"
