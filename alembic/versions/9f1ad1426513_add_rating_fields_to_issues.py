"""add_rating_fields_to_issues

Revision ID: 9f1ad1426513
Revises: 045_user_period_and_analytics_columns
Create Date: 2026-05-02 18:22:54.135708

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9f1ad1426513'
down_revision: Union[str, None] = '045_user_period_and_analytics_columns'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('issues', schema=None) as batch_op:
        batch_op.add_column(sa.Column('rating_quality', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('rating_speed', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('rating_result', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('planned_start_date', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('planned_end_date', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('issues', schema=None) as batch_op:
        batch_op.drop_column('planned_end_date')
        batch_op.drop_column('planned_start_date')
        batch_op.drop_column('rating_result')
        batch_op.drop_column('rating_speed')
        batch_op.drop_column('rating_quality')
