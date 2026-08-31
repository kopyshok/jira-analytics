"""team subgroups

Реестр команд + группы внутри команды, приписка сотрудника и группа у задачи.

Revision ID: 9c30cca1e353
Revises: td05a_team_desk_daily_rate
Create Date: 2026-08-31 16:24:50.530756

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9c30cca1e353'
down_revision: Union[str, None] = 'td05a_team_desk_daily_rate'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())

    if 'teams' not in existing:
        op.create_table(
            'teams',
            sa.Column('id', sa.String(length=36), nullable=False),
            sa.Column('name', sa.String(length=200), nullable=False),
            sa.Column(
                'has_subgroups',
                sa.Boolean(),
                server_default=sa.text('0'),
                nullable=False,
            ),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_teams_name', 'teams', ['name'], unique=True)

    if 'team_subgroups' not in existing:
        op.create_table(
            'team_subgroups',
            sa.Column('id', sa.String(length=36), nullable=False),
            sa.Column('team_id', sa.String(length=36), nullable=False),
            sa.Column('name', sa.String(length=200), nullable=False),
            sa.Column('sort_order', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('team_id', 'name', name='uq_team_subgroup_name'),
        )
        op.create_index(
            'ix_team_subgroups_team_id', 'team_subgroups', ['team_id'], unique=False
        )

    with op.batch_alter_table('employee_teams', schema=None) as batch_op:
        batch_op.add_column(sa.Column('subgroup_id', sa.String(length=36), nullable=True))
        batch_op.create_index(
            batch_op.f('ix_employee_teams_subgroup_id'), ['subgroup_id'], unique=False
        )
        batch_op.create_foreign_key(
            'fk_employee_teams_subgroup',
            'team_subgroups',
            ['subgroup_id'],
            ['id'],
            ondelete='SET NULL',
        )

    with op.batch_alter_table('issues', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('assigned_subgroup_id', sa.String(length=36), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                'subgroup_verified',
                sa.Boolean(),
                server_default=sa.text('1'),
                nullable=False,
            )
        )
        batch_op.create_index(
            batch_op.f('ix_issues_assigned_subgroup_id'),
            ['assigned_subgroup_id'],
            unique=False,
        )
        batch_op.create_foreign_key(
            'fk_issues_assigned_subgroup',
            'team_subgroups',
            ['assigned_subgroup_id'],
            ['id'],
            ondelete='SET NULL',
        )

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'selected_subgroups', sa.Text(), server_default='[]', nullable=False
            )
        )


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('selected_subgroups')

    with op.batch_alter_table('issues', schema=None) as batch_op:
        batch_op.drop_constraint('fk_issues_assigned_subgroup', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_issues_assigned_subgroup_id'))
        batch_op.drop_column('subgroup_verified')
        batch_op.drop_column('assigned_subgroup_id')

    with op.batch_alter_table('employee_teams', schema=None) as batch_op:
        batch_op.drop_constraint('fk_employee_teams_subgroup', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_employee_teams_subgroup_id'))
        batch_op.drop_column('subgroup_id')

    op.drop_index('ix_team_subgroups_team_id', table_name='team_subgroups')
    op.drop_table('team_subgroups')
    op.drop_index('ix_teams_name', table_name='teams')
    op.drop_table('teams')
