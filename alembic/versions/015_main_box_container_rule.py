"""seed 'Main box' container rule

Revision ID: 015_main_box_container_rule
Revises: 014_hierarchy_rules
Create Date: 2026-04-17
"""
from typing import Sequence, Union
import uuid
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision: str = '015_main_box_container_rule'
down_revision: Union[str, None] = '014_hierarchy_rules'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(sa.text(
        "SELECT 1 FROM hierarchy_rule WHERE issue_type = 'Main box' LIMIT 1"
    )).first()
    if existing:
        return
    bind.execute(sa.text(
        "INSERT INTO hierarchy_rule "
        "(id, priority, project_key, issue_type, require_no_parent, "
        " is_container, is_enabled, description, created_at, updated_at) "
        "VALUES (:id, 50, NULL, 'Main box', :require_no_parent, :is_container, :enabled, "
        "'Main box — всегда контейнер', :now, :now)"
    ), {
        "id": str(uuid.uuid4()),
        "require_no_parent": False,
        "is_container": True,
        "enabled": True,
        "now": datetime.utcnow().isoformat(),
    })


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text(
        "DELETE FROM hierarchy_rule WHERE issue_type = 'Main box' "
        "AND description = 'Main box — всегда контейнер'"
    ))
