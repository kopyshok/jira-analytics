"""scheduled_blocks.work_type_id + team_work_type_overrides

Revision ID: nw01_normed_reserve
Revises: pq07_assignment_opo_part
Create Date: 2026-09-28

Заблокированный период — нормированная работа своего вида: он расходует
запас этого вида. Существующие «Закрытие месяца» получают «Сопровождение и
консультация»; остальные остаются без вида (закрывают день, запас не тратят).

Выбор вида работ для задачи другой команды: основная команда исполнителя
указывает, чем для неё считается эта работа (по умолчанию — «Технические
задачи»).

Самодостаточна: не импортирует код приложения. Сравнение причины — в Python:
SQLite lower() не знает кириллицу.
"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

revision: str = "nw01_normed_reserve"
down_revision: Union[str, None] = "pq07_assignment_opo_part"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MONTH_CLOSE = "закрытие месяца"

blocks = sa.table(
    "scheduled_blocks",
    sa.column("id", sa.String),
    sa.column("reason", sa.String),
    sa.column("work_type_id", sa.String),
)
work_types = sa.table("mandatory_work_types", sa.column("id", sa.String), sa.column("code", sa.String))


def upgrade() -> None:
    # Локальная dev-база получает новые таблицы раньше миграции — от
    # create_all в tests/conftest.py. То, что уже есть, пропускаем.
    insp = None if context.is_offline_mode() else sa.inspect(op.get_bind())
    has_column = insp is not None and "work_type_id" in {
        c["name"] for c in insp.get_columns("scheduled_blocks")
    }
    has_table = insp is not None and insp.has_table("team_work_type_overrides")

    if not has_column:
        with op.batch_alter_table("scheduled_blocks") as batch:
            batch.add_column(sa.Column("work_type_id", sa.String(36), nullable=True))
            batch.create_foreign_key(
                "fk_scheduled_blocks_work_type", "mandatory_work_types", ["work_type_id"], ["id"]
            )
    if not has_table:
        _create_overrides()

    # Офлайн-SQL (--sql) данных не видит: заполнение только на живой базе.
    if context.is_offline_mode():
        return
    _fill_month_close()


def _create_overrides() -> None:
    op.create_table(
        "team_work_type_overrides",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("team", sa.String(200), nullable=False),
        sa.Column(
            "backlog_item_id", sa.String(36),
            sa.ForeignKey("backlog_items.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "work_type_id", sa.String(36),
            sa.ForeignKey("mandatory_work_types.id"), nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("team", "backlog_item_id", name="uq_team_work_type_override"),
    )
    op.create_index("ix_team_work_type_overrides_team", "team_work_type_overrides", ["team"])


def _fill_month_close() -> None:
    bind = op.get_bind()
    support = bind.execute(
        sa.select(work_types.c.id).where(work_types.c.code == "support_consult")
    ).scalar()
    if support is None:
        return
    for row in bind.execute(sa.select(blocks.c.id, blocks.c.reason)).all():
        if (row.reason or "").strip().lower() == MONTH_CLOSE:
            bind.execute(blocks.update().where(blocks.c.id == row.id).values(work_type_id=support))


def downgrade() -> None:
    op.drop_index("ix_team_work_type_overrides_team", table_name="team_work_type_overrides")
    op.drop_table("team_work_type_overrides")
    with op.batch_alter_table("scheduled_blocks") as batch:
        batch.drop_constraint("fk_scheduled_blocks_work_type", type_="foreignkey")
        batch.drop_column("work_type_id")
