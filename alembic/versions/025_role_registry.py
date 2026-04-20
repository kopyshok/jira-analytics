"""Role registry."""

from alembic import op
import sqlalchemy as sa

revision = "025_role_registry"
down_revision = "024_backlog_no_quarter_scenario_status"
branch_labels = None
depends_on = None

ROLES_SEED = [
    ("analyst",    "Аналитик",     "#4db8e8", True,  0),
    ("dev",        "Программист",  "#00c9c8", True,  1),
    ("qa",         "Тестировщик",  "#EF9F27", True,  2),
    ("consultant", "Консультант",  "#7F77DD", True,  3),
    ("other",      "Другое",       "#888780", False, 4),
]


def upgrade():
    op.create_table(
        "roles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(64), unique=True, nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("color", sa.String(16), nullable=False, server_default="#888780"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("counts_in_planning", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    import uuid
    conn = op.get_bind()
    for code, label, color, counts, order in ROLES_SEED:
        conn.execute(sa.text(
            "INSERT INTO roles (id, code, label, color, is_active, counts_in_planning, sort_order) "
            "VALUES (:id, :code, :label, :color, 1, :counts, :order)"
        ), {"id": str(uuid.uuid4()), "code": code, "label": label, "color": color,
            "counts": 1 if counts else 0, "order": order})


def downgrade():
    op.drop_table("roles")
