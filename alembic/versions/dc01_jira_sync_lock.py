"""Блокировка синхронизации до переезда на Jira Data Center

Revision ID: dc01_jira_sync_lock
Revises: pf01_perf_metrics
Create Date: 2026-10-14

Ставит AppSetting ``jira_migration_state``: ``pending`` в базе с задачами (их
идентификаторы облачные — синк с новой Jira перезаписал бы чужие строки),
``done`` на свежей установке. Уже заданное значение не трогает.

Самодостаточна: не импортирует код приложения.
"""
import uuid
from datetime import datetime
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

revision: str = "dc01_jira_sync_lock"
down_revision: Union[str, None] = "pf01_perf_metrics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_KEY = "jira_migration_state"


def upgrade() -> None:
    if context.is_offline_mode():
        return
    bind = op.get_bind()
    exists = bind.execute(
        sa.text("SELECT 1 FROM app_settings WHERE key = :key"), {"key": _KEY}
    ).scalar()
    if exists:
        return
    has_issues = bind.execute(sa.text("SELECT 1 FROM issues LIMIT 1")).scalar()
    now = datetime.utcnow()
    bind.execute(
        sa.text(
            "INSERT INTO app_settings (id, key, value, created_at, updated_at) "
            "VALUES (:id, :key, :value, :now, :now)"
        ),
        {
            "id": str(uuid.uuid4()),
            "key": _KEY,
            "value": "pending" if has_issues else "done",
            "now": now,
        },
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("DELETE FROM app_settings WHERE key = :key"), {"key": _KEY}
    )
