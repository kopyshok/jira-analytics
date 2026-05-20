"""reset rp_assignment.pinned_start

Revision ID: 871f7c1d03ab
Revises: b6537be9bb81
Create Date: 2026-05-20 08:15:57.074652

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '871f7c1d03ab'
down_revision: Union[str, None] = 'b6537be9bb81'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Существующие строки могли получить pinned_start=True от split'a
    # (теперь split не пинит даты) и от PATCH'ей до введения явной фиксации.
    # Сбрасываем флаг, чтобы пользователь явно выбирал что закреплять.
    op.execute(
        "UPDATE resource_plan_assignments SET pinned_start = false"
    )


def downgrade() -> None:
    # No-op: данные не восстанавливаются — рестор пина = ручная переустановка.
    pass
