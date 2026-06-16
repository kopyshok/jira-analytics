"""add team to backlog_items

Команда для ручных идей бэклога (issue_id IS NULL), чтобы глобальный фильтр
по команде их не прятал — у ручных идей нет задачи Jira, а значит и Issue.team.

Revision ID: 064_backlog_team
Revises: 063_work_desks
Create Date: 2026-06-16
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "064_backlog_team"
down_revision: Union[str, None] = "063_work_desks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("backlog_items", schema=None) as batch_op:
        batch_op.add_column(sa.Column("team", sa.String(length=200), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_backlog_items_team"), ["team"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("backlog_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_backlog_items_team"))
        batch_op.drop_column("team")
