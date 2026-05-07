"""work_type_thematic_report

Adds:
- themes: dictionary per work_type
- issue_classifications: Map cache
- work_type_report_snapshots: full report cache
- work_type_report_layouts: per-user saved pivot layouts
- mandatory_work_types.theme_dict_version: bumped on dict CRUD

Revision ID: 4c22dff2526e
Revises: c23571f86b16
Create Date: 2026-05-07 20:54:18.404898

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4c22dff2526e'
down_revision: Union[str, None] = 'c23571f86b16'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'themes',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('work_type_id', sa.String(36), sa.ForeignKey('mandatory_work_types.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('color', sa.String(7), nullable=False, server_default='#00c9c8'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_archived', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_by', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('work_type_id', 'name', name='uq_themes_work_type_name'),
    )
    op.create_index('ix_themes_work_type_active', 'themes', ['work_type_id', 'is_archived'])

    op.create_table(
        'issue_classifications',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('issue_id', sa.String(36), sa.ForeignKey('issues.id', ondelete='CASCADE'), nullable=False),
        sa.Column('work_type_id', sa.String(36), sa.ForeignKey('mandatory_work_types.id', ondelete='CASCADE'), nullable=False),
        sa.Column('theme_id', sa.String(36), sa.ForeignKey('themes.id', ondelete='SET NULL'), nullable=True),
        sa.Column('candidate_name', sa.String(255), nullable=True),
        sa.Column('contribution_text', sa.String(500), nullable=True),
        sa.Column('nature_tag', sa.String(32), nullable=True),
        sa.Column('llm_confidence', sa.Float(), nullable=True),
        sa.Column('model_id', sa.String(120), nullable=True),
        sa.Column('prompt_version', sa.String(32), nullable=True),
        sa.Column('input_hash', sa.String(64), nullable=False),
        sa.Column('dictionary_version', sa.Integer(), nullable=False),
        sa.Column('failed', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('failure_reason', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('issue_id', 'work_type_id', name='uq_classifications_issue_wt'),
    )
    op.create_index('ix_classifications_theme', 'issue_classifications', ['theme_id'])

    op.create_table(
        'work_type_report_snapshots',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('work_type_id', sa.String(36), sa.ForeignKey('mandatory_work_types.id', ondelete='CASCADE'), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('quarter', sa.Integer(), nullable=False),
        sa.Column('month', sa.Integer(), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('team_set_hash', sa.String(32), nullable=False),
        sa.Column('team_set_json', sa.Text(), nullable=False),
        sa.Column('snapshot_data', sa.Text(), nullable=False),
        sa.Column('dictionary_version', sa.Integer(), nullable=False),
        sa.Column('model_id', sa.String(120), nullable=True),
        sa.Column('prompt_version', sa.String(32), nullable=True),
        sa.Column('generated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('created_by', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.UniqueConstraint('work_type_id', 'year', 'quarter', 'month', 'team_set_hash', name='uq_wt_report_key'),
    )

    op.create_table(
        'work_type_report_layouts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('work_type_id', sa.String(36), sa.ForeignKey('mandatory_work_types.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('grouping_dims_json', sa.Text(), nullable=False),
        sa.Column('visible_columns_json', sa.Text(), nullable=True),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_layouts_user_wt', 'work_type_report_layouts', ['user_id', 'work_type_id'])

    with op.batch_alter_table('mandatory_work_types', schema=None) as batch_op:
        batch_op.add_column(sa.Column('theme_dict_version', sa.Integer(), nullable=False, server_default='1'))


def downgrade() -> None:
    with op.batch_alter_table('mandatory_work_types', schema=None) as batch_op:
        batch_op.drop_column('theme_dict_version')
    op.drop_index('ix_layouts_user_wt', table_name='work_type_report_layouts')
    op.drop_table('work_type_report_layouts')
    op.drop_table('work_type_report_snapshots')
    op.drop_index('ix_classifications_theme', table_name='issue_classifications')
    op.drop_table('issue_classifications')
    op.drop_index('ix_themes_work_type_active', table_name='themes')
    op.drop_table('themes')
