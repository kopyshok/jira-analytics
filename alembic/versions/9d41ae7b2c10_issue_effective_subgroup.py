"""issue effective subgroup

Материализованная действующая группа задачи — результат лесенки
(явно -> родитель -> исполнитель). Нужна витринам, которые считают агрегаты
в SQL и не могут резолвить группу построчно в Python.

Revision ID: 9d41ae7b2c10
Revises: c94098dd7ead
Create Date: 2026-08-31 18:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9d41ae7b2c10'
down_revision: Union[str, None] = 'c94098dd7ead'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c['name'] for c in sa.inspect(bind).get_columns('issues')}
    if 'effective_subgroup_id' in cols:
        return

    with op.batch_alter_table('issues', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('effective_subgroup_id', sa.String(length=36), nullable=True)
        )
        batch_op.create_index(
            batch_op.f('ix_issues_effective_subgroup_id'),
            ['effective_subgroup_id'],
            unique=False,
        )
        batch_op.create_foreign_key(
            'fk_issues_effective_subgroup',
            'team_subgroups',
            ['effective_subgroup_id'],
            ['id'],
            ondelete='SET NULL',
        )


def downgrade() -> None:
    with op.batch_alter_table('issues', schema=None) as batch_op:
        batch_op.drop_constraint('fk_issues_effective_subgroup', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_issues_effective_subgroup_id'))
        batch_op.drop_column('effective_subgroup_id')
