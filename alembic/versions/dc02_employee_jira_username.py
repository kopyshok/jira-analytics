"""employees.jira_username — логин Jira Data Center

Revision ID: dc02_employee_jira_username
Revises: dc01_jira_sync_lock
Create Date: 2026-10-14

Логин нужен для JQL ``worklogAuthor`` (по ``key`` Jira DC искать не умеет).
Локальная база может уже иметь колонку от create_all в tests/conftest.py —
тогда пропускаем.
"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

revision: str = "dc02_employee_jira_username"
down_revision: Union[str, None] = "dc01_jira_sync_lock"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    if context.is_offline_mode():
        return False
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if not _has_column("employees", "jira_username"):
        with op.batch_alter_table("employees") as batch:
            batch.add_column(sa.Column("jira_username", sa.String(255), nullable=True))


def downgrade() -> None:
    if _has_column("employees", "jira_username"):
        with op.batch_alter_table("employees") as batch:
            batch.drop_column("jira_username")
