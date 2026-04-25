"""QA role color #EF9F27 → #eb2f96 (split from overload amber)."""

from alembic import op
import sqlalchemy as sa


revision = "033_qa_role_color_pink"
down_revision = "032_scenario_revision_item_action_length"
branch_labels = None
depends_on = None


# Старый цвет почти совпадал с amber-перегрузом (#f5a524) — путало взгляд.
# Меняем только если пользователь не перенастроил вручную.
OLD_COLOR = "#EF9F27"
NEW_COLOR = "#eb2f96"


def upgrade():
    op.execute(
        sa.text("UPDATE roles SET color = :new WHERE code = 'qa' AND color = :old")
        .bindparams(new=NEW_COLOR, old=OLD_COLOR)
    )


def downgrade():
    op.execute(
        sa.text("UPDATE roles SET color = :old WHERE code = 'qa' AND color = :new")
        .bindparams(new=NEW_COLOR, old=OLD_COLOR)
    )
