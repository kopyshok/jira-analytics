"""create hierarchy_rule table + seed defaults

Revision ID: 014_hierarchy_rules
Revises: 013_sync_state_scope
Create Date: 2026-04-17
"""
from typing import Sequence, Union
import uuid
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision: str = '014_hierarchy_rules'
down_revision: Union[str, None] = '013_sync_state_scope'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SEED_RULES = [
    # Project-scoped rules — priority 10
    (10, 'ITL', None, True, True, 'ITL без родителя — контейнер'),
    (10, 'RFA', None, False, True, 'RFA всегда контейнер'),
    (10, 'PRJ', None, False, True, 'PRJ всегда контейнер'),
    # Type-scoped rules — priority 50 (preserve pre-014 CONTAINER_ISSUE_TYPES)
    (50, None, 'Эпик', False, True, None),
    (50, None, 'Epic', False, True, None),
    (50, None, 'Инициатива', False, True, None),
    (50, None, 'Инициатива (E-com)', False, True, None),
    (50, None, 'Инициатива (Ритейл)', False, True, None),
    (50, None, 'Инициатива (Финансы)', False, True, None),
    (50, None, 'История', False, True, None),
    (50, None, 'Story', False, True, None),
    (50, None, 'Цель', False, True, None),
]


def upgrade() -> None:
    op.create_table(
        'hierarchy_rule',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('project_key', sa.String(32), nullable=True),
        sa.Column('issue_type', sa.String(128), nullable=True),
        sa.Column('require_no_parent', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('is_container', sa.Boolean(), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('description', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_hierarchy_rule_priority', 'hierarchy_rule', ['priority'])
    op.create_index('ix_hierarchy_rule_project_key', 'hierarchy_rule', ['project_key'])
    op.create_index('ix_hierarchy_rule_issue_type', 'hierarchy_rule', ['issue_type'])

    bind = op.get_bind()
    now = datetime.utcnow().isoformat()
    for priority, project, itype, no_parent, is_container, description in SEED_RULES:
        bind.execute(sa.text(
            "INSERT INTO hierarchy_rule "
            "(id, priority, project_key, issue_type, require_no_parent, "
            " is_container, is_enabled, description, created_at, updated_at) "
            "VALUES (:id, :priority, :project, :itype, :np, :ic, :enabled, :desc, :now, :now)"
        ), {
            "id": str(uuid.uuid4()),
            "priority": priority,
            "project": project,
            "itype": itype,
            "np": no_parent,
            "ic": is_container,
            "enabled": True,
            "desc": description,
            "now": now,
        })


def downgrade() -> None:
    op.drop_index('ix_hierarchy_rule_issue_type', table_name='hierarchy_rule')
    op.drop_index('ix_hierarchy_rule_project_key', table_name='hierarchy_rule')
    op.drop_index('ix_hierarchy_rule_priority', table_name='hierarchy_rule')
    op.drop_table('hierarchy_rule')
