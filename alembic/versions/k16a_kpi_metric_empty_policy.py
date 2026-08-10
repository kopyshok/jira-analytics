"""kpi metric empty policy

Revision ID: k16a_kpi_metric_empty_policy
Revises: kpq01_kpi_approval_quarter
Create Date: 2026-08-10

Правило «что делать, когда данных нет» на уровне отдельной метрики.
NULL — наследовать общее правило раздела.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "k16a_kpi_metric_empty_policy"
down_revision: Union[str, None] = "kpq01_kpi_approval_quarter"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("kpi_metrics") as batch:
        batch.add_column(sa.Column("empty_policy", sa.String(16), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("kpi_metrics") as batch:
        batch.drop_column("empty_policy")
