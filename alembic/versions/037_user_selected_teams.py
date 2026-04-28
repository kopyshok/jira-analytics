"""037 user selected_teams

Revision ID: 037_user_selected_teams
Revises: 036_users
Create Date: 2026-04-28
"""
import json
import sqlalchemy as sa
from alembic import op

revision = "037_user_selected_teams"
down_revision = "036_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column(
                "selected_teams",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, default_team FROM users")).fetchall()
    for row in rows:
        if row.default_team:
            payload = json.dumps([row.default_team])
            bind.execute(
                sa.text("UPDATE users SET selected_teams = :p WHERE id = :id"),
                {"p": payload, "id": row.id},
            )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("selected_teams")
