"""resource_plans: отпечаток броней других команд, учтённых при расчёте

Revision ID: pq06_plan_external_fingerprint
Revises: pq05_backlog_assignee_manual
Create Date: 2026-09-24

Самодостаточна: не импортирует код приложения.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "pq06_plan_external_fingerprint"
down_revision: Union[str, None] = "pq05_backlog_assignee_manual"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("resource_plans") as batch:
        batch.add_column(sa.Column("external_fingerprint", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("resource_plans") as batch:
        batch.drop_column("external_fingerprint")
