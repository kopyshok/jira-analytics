"""kpi: сроки считаются только по эпикам подтипов PROJECT и RFC_STANDARD

Уточнение заказчика. Метрика оценивает выполнение квартальной цели в срок,
а эпики операционной работы квартальными целями не являются: у сотрудника
из десяти закрытых за месяц эпиков девять оказывались операционными и без
плановой даты. Отбор по подтипу совпадает с тем, что уже применён в Cycle
Time и оценке заказчика.

Правит только встроенную метрику и только если условие подтипа ещё не
добавлено — метрики, заведённые руководителем вручную, не трогает.

Revision ID: k11a_kpi_deadlines_subtype_scope
Revises: k10a_kpi_fix_resolution_and_deadlines_scope
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "k11a_kpi_deadlines_subtype_scope"
down_revision = "k10a_kpi_fix_resolution_and_deadlines_scope"
branch_labels = None
depends_on = None

SUBTYPES = ["RFC_STANDARD", "PROJECT"]
SUBTYPE_CONDITION = {"attr": "subtype", "op": "in", "value": SUBTYPES}


def _rewrite(raw: str, add: bool) -> str:
    """Добавить или убрать условие подтипа в наборе условий метрики."""
    data = json.loads(raw)
    conditions = data.get("conditions", [])
    has_subtype = any(c.get("attr") == "subtype" for c in conditions)
    if add and not has_subtype:
        # После типа задачи, чтобы порядок условий читался как в справочнике.
        insert_at = next(
            (i + 1 for i, c in enumerate(conditions) if c.get("attr") == "issue_type"),
            0,
        )
        conditions.insert(insert_at, dict(SUBTYPE_CONDITION))
    elif not add and has_subtype:
        conditions = [c for c in conditions if c.get("attr") != "subtype"]
    data["conditions"] = conditions
    return json.dumps(data, ensure_ascii=False)


def _apply(add: bool) -> None:
    bind = op.get_bind()
    row = bind.execute(
        sa.text(
            "SELECT numerator_json, denominator_json FROM kpi_metrics "
            "WHERE code = 'deadlines' AND is_builtin = true"
        )
    ).fetchone()
    if row is None:
        return
    bind.execute(
        sa.text(
            "UPDATE kpi_metrics SET numerator_json = :num, denominator_json = :den "
            "WHERE code = 'deadlines' AND is_builtin = true"
        ),
        {"num": _rewrite(row[0], add), "den": _rewrite(row[1], add)},
    )


def upgrade() -> None:
    _apply(add=True)


def downgrade() -> None:
    _apply(add=False)
