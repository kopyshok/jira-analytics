"""jira_migration_reports + jira_migration_decisions

Revision ID: dc03_jira_migration_tables
Revises: dc02_employee_jira_username
Create Date: 2026-10-14

Отчёт пробного прогона переезда на Jira Data Center и решения
администратора. Самодостаточна: не импортирует код приложения. Локальная
база может уже иметь таблицы от create_all в tests/conftest.py — такие
пропускаем.
"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

revision: str = "dc03_jira_migration_tables"
down_revision: Union[str, None] = "dc02_employee_jira_username"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has(table: str) -> bool:
    if context.is_offline_mode():
        return False
    return sa.inspect(op.get_bind()).has_table(table)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    if not _has("jira_migration_reports"):
        op.create_table(
            "jira_migration_reports",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("report_json", sa.Text(), nullable=True),
            sa.Column("maps_json", sa.Text(), nullable=True),
            sa.Column("applied_at", sa.DateTime(), nullable=True),
            sa.Column("apply_summary_json", sa.Text(), nullable=True),
            sa.Column("sync_run_id", sa.String(36), nullable=True),
            sa.Column("post_check_json", sa.Text(), nullable=True),
            *_timestamps(),
        )
    if not _has("jira_migration_decisions"):
        op.create_table(
            "jira_migration_decisions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("kind", sa.String(16), nullable=False),
            sa.Column("item_key", sa.String(128), nullable=False),
            sa.Column("decision_json", sa.Text(), nullable=False),
            sa.Column("decided_by", sa.String(255), nullable=True),
            *_timestamps(),
            sa.UniqueConstraint("kind", "item_key", name="uq_jira_migration_decision"),
        )


def downgrade() -> None:
    if _has("jira_migration_decisions"):
        op.drop_table("jira_migration_decisions")
    if _has("jira_migration_reports"):
        op.drop_table("jira_migration_reports")
