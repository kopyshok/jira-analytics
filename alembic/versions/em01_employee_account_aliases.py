"""employee_account_aliases

Revision ID: em01_employee_account_aliases
Revises: dc05_console_runs
Create Date: 2026-10-21

Старые учётки Jira слитых сотрудников. Самодостаточна: не импортирует код
приложения. Локальная база может уже иметь таблицу от create_all в
tests/conftest.py — тогда пропускаем.
"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

revision: str = "em01_employee_account_aliases"
down_revision: Union[str, None] = "dc05_console_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has(table: str) -> bool:
    if context.is_offline_mode():
        return False
    return sa.inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    if _has("employee_account_aliases"):
        return
    op.create_table(
        "employee_account_aliases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("jira_account_id", sa.String(128), nullable=False, unique=True),
        sa.Column(
            "employee_id", sa.String(36),
            sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_employee_account_aliases_employee_id", "employee_account_aliases", ["employee_id"],
    )


def downgrade() -> None:
    if _has("employee_account_aliases"):
        op.drop_index("ix_employee_account_aliases_employee_id", table_name="employee_account_aliases")
        op.drop_table("employee_account_aliases")
