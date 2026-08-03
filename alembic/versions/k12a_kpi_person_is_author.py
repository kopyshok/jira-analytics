"""kpi: все встроенные метрики считаются по автору задачи, а не по исполнителю

Решение заказчика: показатель принадлежит тому, кто задачу поставил и
сформулировал, а не тому, на кого она назначена. До этой миграции
«Соблюдение сроков», Cycle Time и «Оценка заказчика» считались по
исполнителю; у «Качества выпуска» в уже развёрнутых базах признак был
вручную переставлен на исполнителя через справочник.

Числитель «Качества выпуска» — особый случай: там считаются не задачи
человека, а баги на проде, связанные с его задачами, поэтому «автор» для
него означает «автор связанной задачи».

Правит только встроенные метрики (``is_builtin = true``) — метрики,
заведённые руководителем вручную, не трогает. Идемпотентна.

Обратимость — с той же оговоркой, что у ``k10a``: ``downgrade`` возвращает
исполнителя безусловно, отличить «эту строку поправил я» от «она и так была
такой» без отдельной истории нельзя.

Revision ID: k12a_kpi_person_is_author
Revises: k11a_kpi_deadlines_subtype_scope
"""
import json
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "k12a_kpi_person_is_author"
down_revision: Union[str, None] = "k11a_kpi_deadlines_subtype_scope"
branch_labels = None
depends_on = None

# code → (признак числителя, признак знаменателя); None — сторону не трогаем.
UPGRADE_TARGETS = {
    "quality": ("linked_issue_author", "author"),
    "deadlines": ("author", "author"),
    "regulations": ("author", "author"),
    "cycle_time": ("author", None),
    "customer_score": ("author", None),
}
DOWNGRADE_TARGETS = {
    "quality": ("linked_issue_author", "author"),
    "deadlines": ("assignee", "assignee"),
    "regulations": ("author", "author"),
    "cycle_time": ("assignee", None),
    "customer_score": ("assignee", None),
}

OLD_DEADLINES_DESCRIPTION = "Доля задач исполнителя, выполненных не позже плановой даты окончания"
NEW_DEADLINES_DESCRIPTION = "Доля задач автора, выполненных не позже плановой даты окончания"


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
