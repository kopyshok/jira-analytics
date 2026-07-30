"""kpi: явный признак профиля по умолчанию

Revision ID: k08a_kpi_profile_is_default
Revises: k07a_kpi_seed_defaults
Create Date: 2026-07-30
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "k08a_kpi_profile_is_default"
down_revision: Union[str, None] = "k07a_kpi_seed_defaults"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("kpi_profiles") as batch:
        batch.add_column(
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    # Профиль «Аналитик», заведённый сидом (Task 12), становится запасным
    # по умолчанию — тем же, что и раньше подставлялся неявно первым по
    # выборке. Теперь это осознанная настройка, а не порядок строк в БД.
    op.execute("UPDATE kpi_profiles SET is_default = true WHERE code = 'analyst'")


def downgrade() -> None:
    with op.batch_alter_table("kpi_profiles") as batch:
        batch.drop_column("is_default")
