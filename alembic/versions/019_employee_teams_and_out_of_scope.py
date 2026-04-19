"""employee_teams table + issues.out_of_scope + data migration

Revision ID: 019_employee_teams_and_out_of_scope
Revises: 018_rename_vacations_to_absences
Create Date: 2026-04-19
"""
from typing import Sequence, Union
import uuid
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision: str = '019_employee_teams_and_out_of_scope'
down_revision: Union[str, None] = '018_rename_vacations_to_absences'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. employee_teams
    op.create_table(
        'employee_teams',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('employee_id', sa.String(36), nullable=False),
        sa.Column('team', sa.String(100), nullable=False),
        sa.Column('is_primary', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ['employee_id'], ['employees.id'],
            ondelete='CASCADE',
            name='fk_employee_teams_employee_id',
        ),
        sa.UniqueConstraint('employee_id', 'team', name='uq_employee_teams_employee_team'),
    )
    op.create_index('ix_employee_teams_employee_id', 'employee_teams', ['employee_id'])
    op.create_index('ix_employee_teams_team', 'employee_teams', ['team'])

    # 2. issues.out_of_scope
    with op.batch_alter_table('issues') as batch:
        batch.add_column(sa.Column(
            'out_of_scope', sa.Boolean(),
            nullable=False, server_default=sa.false(),
        ))
    op.create_index('ix_issues_out_of_scope', 'issues', ['out_of_scope'])

    # 3. Data migration: copy employees.team → employee_teams(is_primary=true)
    bind = op.get_bind()
    now = datetime.utcnow().isoformat()
    rows = bind.execute(sa.text(
        "SELECT id, team FROM employees WHERE team IS NOT NULL AND team != ''"
    )).fetchall()
    for emp_id, team in rows:
        bind.execute(sa.text(
            "INSERT INTO employee_teams (id, employee_id, team, is_primary, created_at) "
            "VALUES (:id, :eid, :team, 1, :now)"
        ), {"id": str(uuid.uuid4()), "eid": emp_id, "team": team, "now": now})


def downgrade() -> None:
    op.drop_index('ix_issues_out_of_scope', table_name='issues')
    with op.batch_alter_table('issues') as batch:
        batch.drop_column('out_of_scope')

    op.drop_index('ix_employee_teams_team', table_name='employee_teams')
    op.drop_index('ix_employee_teams_employee_id', table_name='employee_teams')
    op.drop_table('employee_teams')
