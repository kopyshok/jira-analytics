"""plan hours versioning: rename + manual fields

Revision ID: 058_plan_hours_versioning
Revises: 057_seed_release_notes
Create Date: 2026-06-03
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "058_plan_hours_versioning"
down_revision: Union[str, None] = "057_seed_release_notes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLES = ("analyst", "dev", "qa", "opo")


def upgrade() -> None:
    with op.batch_alter_table("issues") as batch:
        for role in ROLES:
            batch.alter_column(
                f"planned_{role}_hours",
                new_column_name=f"planned_{role}_hours_jira",
            )
            batch.add_column(
                sa.Column(f"planned_{role}_hours_manual", sa.Float(), nullable=True)
            )


def downgrade() -> None:
    with op.batch_alter_table("issues") as batch:
        for role in ROLES:
            batch.drop_column(f"planned_{role}_hours_manual")
            batch.alter_column(
                f"planned_{role}_hours_jira",
                new_column_name=f"planned_{role}_hours",
            )
