"""kpi: сроки, Cycle Time и оценка заказчика считаются по исполнителю

Решение заказчика поверх ``k12a``: три метрики возвращаются на исполнителя.
Это совпадает с SQL дашборда из ТЗ, где ``t_metric``, ``ct_metric`` и
``oz_metric`` группируются по ``assignee``, а ``b_metric`` и ``r_metric`` — по
``reporter``.

Правит только встроенные метрики (``is_builtin = true``) и только те стороны
формулы, которые ``k12a`` до этого перевёл на автора — метрики, заведённые
руководителем вручную, не трогает. Идемпотентна.

Revision ID: k14a_kpi_person_assignee
Revises: k13a_kpi_profile_roles
"""
import json
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "k14a_kpi_person_assignee"
down_revision: Union[str, None] = "k13a_kpi_profile_roles"
branch_labels = None
depends_on = None

# code → (признак числителя, признак знаменателя); None — сторону не трогаем.
UPGRADE_TARGETS = {
    "deadlines": ("assignee", "assignee"),
    "cycle_time": ("assignee", None),
    "customer_score": ("assignee", None),
}
DOWNGRADE_TARGETS = {
    "deadlines": ("author", "author"),
    "cycle_time": ("author", None),
    "customer_score": ("author", None),
}

NEW_DEADLINES_DESCRIPTION = "Доля задач исполнителя, выполненных не позже плановой даты окончания"
OLD_DEADLINES_DESCRIPTION = "Доля задач автора, выполненных не позже плановой даты окончания"


def _set_person(raw, person_field):
    """Переставить «кто считается» в наборе условий; вернуть (json, изменилось ли)."""
    if not raw or person_field is None:
        return raw, False
    data = json.loads(raw)
    if data.get("person_field") == person_field:
        return raw, False
    data["person_field"] = person_field
    return json.dumps(data, ensure_ascii=False), True


def _apply(targets, description) -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT id, code, numerator_json, denominator_json FROM kpi_metrics WHERE is_builtin = true"
    )).fetchall()
    for metric_id, code, num_json, den_json in rows:
        if code not in targets:
            continue
        num_target, den_target = targets[code]
        num_json, num_changed = _set_person(num_json, num_target)
        den_json, den_changed = _set_person(den_json, den_target)
        if num_changed or den_changed:
            bind.execute(
                sa.text(
                    "UPDATE kpi_metrics SET numerator_json = :num, denominator_json = :den "
                    "WHERE id = :id"
                ),
                {"num": num_json, "den": den_json, "id": metric_id},
            )
    bind.execute(
        sa.text(
            "UPDATE kpi_metrics SET description = :desc "
            "WHERE code = 'deadlines' AND is_builtin = true"
        ),
        {"desc": description},
    )


def upgrade() -> None:
    _apply(UPGRADE_TARGETS, NEW_DEADLINES_DESCRIPTION)


def downgrade() -> None:
    _apply(DOWNGRADE_TARGETS, OLD_DEADLINES_DESCRIPTION)
