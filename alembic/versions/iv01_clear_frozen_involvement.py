"""Вовлечённость — только из сервиса: снять проценты задач, убрать поля Jira

Revision ID: iv01_clear_frozen_involvement
Revises: ob01_onboarding
Create Date: 2026-09-30

Процент вовлечённости у задачи бэклога раньше приходил из Jira и копировался
из справочника при утверждении сценария — и перекрывал справочник. Теперь
процент задачи — это только фиксация, поставленная в фазе ресурсного плана,
поэтому все прежние значения снимаются (фазы берут личную настройку сотрудника
или справочник команды), а колонки вовлечённости у задач Jira удаляются —
синхронизация их больше не заполняет. Самодостаточна: не импортирует код
приложения.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "iv01_clear_frozen_involvement"
down_revision: Union[str, None] = "ob01_onboarding"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FIELDS = ("involvement_analyst", "involvement_dev", "involvement_qa", "involvement_launch")


def upgrade() -> None:
    items = sa.table("backlog_items", *(sa.column(f) for f in FIELDS))
    op.execute(items.update().values({f: None for f in FIELDS}))

    if context.is_offline_mode():
        present = set(FIELDS)
    else:
        present = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("issues")}
    to_drop = [f for f in FIELDS if f in present]
    if to_drop:
        with op.batch_alter_table("issues", schema=None) as batch_op:
            for f in to_drop:
                batch_op.drop_column(f)


def downgrade() -> None:
    # Значения не восстанавливаются: колонки вернутся пустыми.
    with op.batch_alter_table("issues", schema=None) as batch_op:
        for f in FIELDS:
            batch_op.add_column(sa.Column(f, sa.Float(), nullable=True))
