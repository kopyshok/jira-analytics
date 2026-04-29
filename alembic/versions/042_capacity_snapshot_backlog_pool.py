"""scenario_capacity_snapshot.backlog_pool_hours

Сохраняем «На бэклог» (часы на инициативы после вычета обязательных работ)
per-сотрудник × месяц на момент утверждения сценария.

Revision ID: 042
Revises: 041
Create Date: 2026-04-29
"""
from alembic import op
import sqlalchemy as sa

revision = '042'
down_revision = '041'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("scenario_capacity_snapshots") as batch_op:
        batch_op.add_column(sa.Column("backlog_pool_hours", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("scenario_capacity_snapshots") as batch_op:
        batch_op.drop_column("backlog_pool_hours")
