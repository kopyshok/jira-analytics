"""Renaming vacations → absences + reason.

Revision ID: 018_rename_vacations_to_absences
Revises: 017_production_calendar_hours
Create Date: 2026-04-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "018_rename_vacations_to_absences"
down_revision: Union[str, None] = "017_production_calendar_hours"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table("vacations", "absences")
    with op.batch_alter_table("absences") as batch_op:
        batch_op.add_column(
            sa.Column(
                "reason",
                sa.String(32),
                nullable=False,
                server_default="vacation",
            ),
        )
    # Ensure all existing rows carry the default reason explicitly.
    op.execute("UPDATE absences SET reason='vacation' WHERE reason IS NULL OR reason=''")


def downgrade() -> None:
    with op.batch_alter_table("absences") as batch_op:
        batch_op.drop_column("reason")
    op.rename_table("absences", "vacations")
