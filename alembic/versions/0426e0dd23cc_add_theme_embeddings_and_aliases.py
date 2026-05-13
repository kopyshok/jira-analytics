"""add theme embeddings and aliases

Revision ID: 0426e0dd23cc
Revises: bb795d2bd202
Create Date: 2026-05-13 21:33:48.882114

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0426e0dd23cc'
down_revision: Union[str, None] = 'bb795d2bd202'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("themes") as batch:
        batch.add_column(sa.Column("embedding", sa.LargeBinary, nullable=True))
        batch.add_column(sa.Column("embedding_model_version", sa.String(64), nullable=True))
        batch.add_column(sa.Column("embedding_updated_at", sa.DateTime, nullable=True))
        batch.add_column(sa.Column("aliases_json", sa.Text, nullable=True))

    with op.batch_alter_table("issue_classifications") as batch:
        batch.add_column(sa.Column("input_embedding", sa.LargeBinary, nullable=True))
        batch.add_column(sa.Column("embedding_model_version", sa.String(64), nullable=True))
        batch.add_column(sa.Column("match_method", sa.String(16), nullable=True))
        batch.add_column(sa.Column("match_score", sa.Float, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("issue_classifications") as batch:
        batch.drop_column("match_score")
        batch.drop_column("match_method")
        batch.drop_column("embedding_model_version")
        batch.drop_column("input_embedding")

    with op.batch_alter_table("themes") as batch:
        batch.drop_column("aliases_json")
        batch.drop_column("embedding_updated_at")
        batch.drop_column("embedding_model_version")
        batch.drop_column("embedding")
