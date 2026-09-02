"""hierarchy_rule.require_parent + seed rule: child epics of RFA are not initiatives

Revision ID: hr01_rule_require_parent
Revises: 9d41ae7b2c10
Create Date: 2026-09-01
"""
from typing import Sequence, Union
import uuid
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision: str = 'hr01_rule_require_parent'
down_revision: Union[str, None] = '9d41ae7b2c10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEED_DESCRIPTION = 'Эпик внутри RFA (авто-Discovery) — не инициатива'


def upgrade() -> None:
    with op.batch_alter_table('hierarchy_rule') as batch:
        batch.add_column(
            sa.Column('require_parent', sa.Boolean(), nullable=False, server_default=sa.false())
        )

    bind = op.get_bind()
    # Сид только там, где RFA-проект реально настроен (боевой тенант).
    has_rfa = bind.execute(sa.text(
        "SELECT 1 FROM hierarchy_rule WHERE project_key = 'RFA' LIMIT 1"
    )).first()
    exists = bind.execute(sa.text(
        "SELECT 1 FROM hierarchy_rule WHERE description = :d LIMIT 1"
    ), {"d": SEED_DESCRIPTION}).first()
    if has_rfa and not exists:
        bind.execute(sa.text(
            "INSERT INTO hierarchy_rule "
            "(id, priority, project_key, issue_type, require_no_parent, require_parent, "
            " is_container, is_enabled, description, created_at, updated_at) "
            "VALUES (:id, 5, 'RFA', 'Эпик', :f, :t, :f, :t, :d, :now, :now)"
        ), {
            "id": str(uuid.uuid4()),
            "t": True,
            "f": False,
            "d": SEED_DESCRIPTION,
            "now": datetime.utcnow().isoformat(),
        })


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM hierarchy_rule WHERE description = :d"), {"d": SEED_DESCRIPTION})
    with op.batch_alter_table('hierarchy_rule') as batch:
        batch.drop_column('require_parent')
