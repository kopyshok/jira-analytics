"""console_runs

Revision ID: dc05_console_runs
Revises: dc04_drop_local_embeddings
Create Date: 2026-10-16

История консоли Jira/Confluence в админке. Самодостаточна: не импортирует
код приложения. Локальная база может уже иметь таблицу от create_all в
tests/conftest.py — тогда пропускаем.
"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

revision: str = "dc05_console_runs"
down_revision: Union[str, None] = "dc04_drop_local_embeddings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has(table: str) -> bool:
    if context.is_offline_mode():
        return False
    return sa.inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    if _has("console_runs"):
        return
    op.create_table(
        "console_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("user_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("target", sa.String(16), nullable=False),
        sa.Column("masked", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("output_text", sa.Text(), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_console_runs_created_at", "console_runs", ["created_at"])


def downgrade() -> None:
    if _has("console_runs"):
        op.drop_index("ix_console_runs_created_at", table_name="console_runs")
        op.drop_table("console_runs")
