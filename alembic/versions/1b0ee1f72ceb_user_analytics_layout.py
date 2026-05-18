"""user_analytics_layout

Revision ID: 1b0ee1f72ceb
Revises: 48d695d53b0d
Create Date: 2026-05-18 23:23:54.541121

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1b0ee1f72ceb'
down_revision: Union[str, None] = '48d695d53b0d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column(
                "analytics_layout",
                sa.Text(),
                nullable=False,
                server_default="{}",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("analytics_layout")
