"""create_project_ai_summary

Revision ID: cc4e80e172fa
Revises: 9f1ad1426513
Create Date: 2026-05-02 18:25:41.531706

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cc4e80e172fa'
down_revision: Union[str, None] = '9f1ad1426513'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'project_ai_summaries',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('issue_id', sa.String(36),
                  sa.ForeignKey('issues.id', ondelete='CASCADE'),
                  nullable=False, unique=True, index=True),
        sa.Column('goals_json', sa.Text(), nullable=False),
        sa.Column('result_flow_json', sa.Text(), nullable=False),
        sa.Column('result_checklist_json', sa.Text(), nullable=False),
        sa.Column('status_text', sa.Text(), nullable=False),
        sa.Column('workload_summary', sa.Text(), nullable=False),
        sa.Column('generated_at', sa.DateTime(), nullable=False,
                  server_default=sa.func.now()),
        sa.Column('model_used', sa.String(64), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('prompt_version', sa.String(32), nullable=False, server_default='v1'),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False,
                  server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('project_ai_summaries')
