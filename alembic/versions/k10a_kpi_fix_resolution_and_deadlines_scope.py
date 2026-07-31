"""kpi: починить резолюцию встроенных метрик (Готово→Done) и сузить «Соблюдение сроков» до эпиков

Revision ID: k10a_kpi_fix_resolution_and_deadlines_scope
Revises: k09a_kpi_hidden_by_default
Create Date: 2026-07-31

Две находки на реальных данных арендатора (~115k задач):

1. Все встроенные метрики заведены с условием «резолюция = Готово»
   (``app/services/kpi/seed.py``), а у этого арендатора Jira значение
   резолюции называется Done. Четыре метрики из шести не находили ни одной
   задачи — отчёт показывал «нет данных» почти везде.
2. «Соблюдение сроков» оценивает выполнение квартальной цели, а квартальная
   цель — эпик (уточнение заказчика поверх ТЗ). До этой миграции в условие
   попадала ещё и «ИТ-задача».

Правит только встроенные метрики (``is_builtin = true``) и только эти два
значения внутри условий — метрики, заведённые руководителем вручную, не
трогает. Идемпотентна (повторный запуск ничего не меняет).

**Обратимость — с оговоркой.** ``downgrade`` меняет значения назад
безусловно (тот же принцип, что и ``upgrade``), поэтому корректно отменяет
именно результат этой миграции сразу после её применения. На базе, где
``upgrade`` был no-op (данные уже верны — например, свежая база, заведённая
уже исправленным ``app/services/kpi/seed.py``), ``downgrade`` всё равно
откатит их к старым значениям: у миграции нет способа отличить «эту строку
поправил я» от «она и так была верна» без отдельной таблицы истории, которую
здесь заводить избыточно. Тот же компромисс уже есть у ``k07a`` (её
``downgrade`` удаляет ВСЕ встроенные метрики без разбора, откуда они взялись).
"""
import json
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "k10a_kpi_fix_resolution_and_deadlines_scope"
down_revision: Union[str, None] = "k09a_kpi_hidden_by_default"
branch_labels = None
depends_on = None

_OLD_RESOLUTION = "Готово"
_NEW_RESOLUTION = "Done"
_IT_TASK = "ИТ-задача"


def _swap_value(raw: str | None, attr: str, old: str, new: str) -> tuple[str | None, bool]:
    """Заменить ``old`` на ``new`` внутри ``condition.value`` (список) для атрибута ``attr``."""
    if not raw:
        return raw, False
    data = json.loads(raw)
    changed = False
    for cond in data.get("conditions", []):
        if cond.get("attr") != attr:
            continue
        values = cond.get("value")
        if isinstance(values, list) and old in values:
            cond["value"] = [new if v == old else v for v in values]
            changed = True
    return (json.dumps(data, ensure_ascii=False) if changed else raw), changed


def _remove_value(raw: str | None, attr: str, value: str) -> tuple[str | None, bool]:
    """Убрать ``value`` из списка ``condition.value`` для атрибута ``attr``, если он там есть."""
    if not raw:
        return raw, False
    data = json.loads(raw)
    changed = False
    for cond in data.get("conditions", []):
        if cond.get("attr") != attr:
            continue
        values = cond.get("value")
        if isinstance(values, list) and value in values:
            cond["value"] = [v for v in values if v != value]
            changed = True
    return (json.dumps(data, ensure_ascii=False) if changed else raw), changed


def _add_value(raw: str | None, attr: str, value: str) -> tuple[str | None, bool]:
    """Добавить ``value`` в список ``condition.value`` для атрибута ``attr``, если его там ещё нет."""
    if not raw:
        return raw, False
    data = json.loads(raw)
    changed = False
    for cond in data.get("conditions", []):
        if cond.get("attr") != attr:
            continue
        values = cond.get("value")
        if isinstance(values, list) and value not in values:
            cond["value"] = [*values, value]
            changed = True
    return (json.dumps(data, ensure_ascii=False) if changed else raw), changed


def _rewrite_builtin_metrics(bind, resolution_swap, deadlines_issue_type_edit) -> None:
    """Общий проход по встроенным метрикам для upgrade/downgrade — только разное направление правок."""
    rows = bind.execute(sa.text(
        "SELECT id, code, numerator_json, denominator_json FROM kpi_metrics WHERE is_builtin = true"
    )).fetchall()
    for metric_id, code, num_json, den_json in rows:
        num_json, num_res_changed = resolution_swap(num_json)
        den_json, den_res_changed = resolution_swap(den_json)
        num_it_changed = den_it_changed = False
        if code == "deadlines":
            num_json, num_it_changed = deadlines_issue_type_edit(num_json)
            den_json, den_it_changed = deadlines_issue_type_edit(den_json)
        if num_res_changed or den_res_changed or num_it_changed or den_it_changed:
            bind.execute(
                sa.text(
                    "UPDATE kpi_metrics SET numerator_json = :num, denominator_json = :den "
                    "WHERE id = :id"
                ),
                {"num": num_json, "den": den_json, "id": metric_id},
            )


def upgrade() -> None:
    bind = op.get_bind()
    _rewrite_builtin_metrics(
        bind,
        resolution_swap=lambda raw: _swap_value(raw, "resolution", _OLD_RESOLUTION, _NEW_RESOLUTION),
        deadlines_issue_type_edit=lambda raw: _remove_value(raw, "issue_type", _IT_TASK),
    )


def downgrade() -> None:
    bind = op.get_bind()
    _rewrite_builtin_metrics(
        bind,
        resolution_swap=lambda raw: _swap_value(raw, "resolution", _NEW_RESOLUTION, _OLD_RESOLUTION),
        deadlines_issue_type_edit=lambda raw: _add_value(raw, "issue_type", _IT_TASK),
    )
