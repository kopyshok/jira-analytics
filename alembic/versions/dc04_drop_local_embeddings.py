"""drop local embedding columns

Локальная модель подбора тем убрана: тему задаче подбирает только облачный LLM.
Векторы тем и задач больше не считаются и не читаются.

Revision ID: dc04_drop_local_embeddings
Revises: dc03_jira_migration_tables
Create Date: 2026-10-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'dc04_drop_local_embeddings'
down_revision: Union[str, None] = 'dc03_jira_migration_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DROPPED = {
    "themes": ["embedding", "embedding_model_version", "embedding_updated_at"],
    "issue_classifications": [
        "input_embedding", "embedding_model_version", "match_method", "match_score",
    ],
}


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    for table, columns in _DROPPED.items():
        # Таблицу могли создать по уже новой модели (create_all в тестах) — колонок там нет.
        existing = {c["name"] for c in insp.get_columns(table)}
        present = [c for c in columns if c in existing]
        if not present:
            continue
        with op.batch_alter_table(table) as batch:
            for col in present:
                batch.drop_column(col)


def downgrade() -> None:
    with op.batch_alter_table("themes") as batch:
        batch.add_column(sa.Column("embedding", sa.LargeBinary, nullable=True))
        batch.add_column(sa.Column("embedding_model_version", sa.String(64), nullable=True))
        batch.add_column(sa.Column("embedding_updated_at", sa.DateTime, nullable=True))

    with op.batch_alter_table("issue_classifications") as batch:
        batch.add_column(sa.Column("input_embedding", sa.LargeBinary, nullable=True))
        batch.add_column(sa.Column("embedding_model_version", sa.String(64), nullable=True))
        batch.add_column(sa.Column("match_method", sa.String(16), nullable=True))
        batch.add_column(sa.Column("match_score", sa.Float, nullable=True))
