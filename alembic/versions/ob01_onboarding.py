"""«Первые шаги»: отметки шагов команды и личное состояние пользователя

Revision ID: ob01_onboarding
Revises: pq07_assignment_opo_part
Create Date: 2026-09-28

Таблица могла быть создана раньше (create_all в тестах на локальной базе) —
создаётся только если её нет. Самодостаточна: не импортирует код приложения.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "ob01_onboarding"
down_revision: Union[str, None] = "pq07_assignment_opo_part"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "team_onboarding_marks" not in inspector.get_table_names():
        op.create_table(
            "team_onboarding_marks",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("team", sa.String(length=200), nullable=False),
            sa.Column("step", sa.String(length=50), nullable=False),
            sa.Column("state", sa.String(length=16), nullable=False),
            sa.Column("source", sa.String(length=16), nullable=False),
            sa.Column("marked_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("marked_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["marked_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("team", "step", name="uq_team_onboarding_mark"),
        )
        op.create_index("ix_team_onboarding_marks_team", "team_onboarding_marks", ["team"])

    user_cols = {c["name"] for c in inspector.get_columns("users")}
    if "onboarding" not in user_cols:
        with op.batch_alter_table("users") as batch:
            batch.add_column(
                sa.Column("onboarding", sa.Text(), nullable=False, server_default="{}")
            )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("onboarding")
    op.drop_index("ix_team_onboarding_marks_team", table_name="team_onboarding_marks")
    op.drop_table("team_onboarding_marks")
