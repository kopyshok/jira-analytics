"""perf_minute + perf_slow_request + perf_server_snapshot

Revision ID: pf01_perf_metrics
Revises: iv01_clear_frozen_involvement
Create Date: 2026-10-04

Замеры быстродействия для раздела админа «Быстродействие»: минутные агрегаты
запросов по шаблону пути, медленные запросы с деталями, снимки нагрузки
сервера. Хранятся 30 дней, чистит фоновый цикл приложения.

Самодостаточна: не импортирует код приложения. Локальная dev-база может
уже иметь таблицы от create_all в tests/conftest.py — такие пропускаем.
"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

revision: str = "pf01_perf_metrics"
down_revision: Union[str, None] = "iv01_clear_frozen_involvement"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has(table: str) -> bool:
    if context.is_offline_mode():
        return False
    return sa.inspect(op.get_bind()).has_table(table)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    if not _has("perf_minute"):
        op.create_table(
            "perf_minute",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("minute", sa.DateTime(), nullable=False),
            sa.Column("method", sa.String(10), nullable=False),
            sa.Column("route", sa.String(300), nullable=False),
            sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("total_ms", sa.Float(), nullable=False, server_default="0"),
            sa.Column("max_ms", sa.Float(), nullable=False, server_default="0"),
            sa.Column("errors_5xx", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("db_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("db_ms", sa.Float(), nullable=False, server_default="0"),
            *[
                sa.Column(f"h{i}", sa.Integer(), nullable=False, server_default="0")
                for i in range(11)
            ],
            *_timestamps(),
        )
        op.create_index("ix_perf_minute_minute", "perf_minute", ["minute"])
        op.create_index("ix_perf_minute_route_minute", "perf_minute", ["route", "minute"])

    if not _has("perf_slow_request"):
        op.create_table(
            "perf_slow_request",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("at", sa.DateTime(), nullable=False),
            sa.Column("method", sa.String(10), nullable=False),
            sa.Column("route", sa.String(300), nullable=False),
            sa.Column("path", sa.String(500), nullable=False),
            sa.Column("query", sa.Text(), nullable=False, server_default=""),
            sa.Column("status_code", sa.Integer(), nullable=False),
            sa.Column("duration_ms", sa.Float(), nullable=False),
            sa.Column("db_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("db_ms", sa.Float(), nullable=False, server_default="0"),
            sa.Column("cpu_ms", sa.Float(), nullable=False, server_default="0"),
            sa.Column("user_id", sa.String(36), nullable=True),
            sa.Column("top_queries", sa.JSON(), nullable=False),
            *_timestamps(),
        )
        op.create_index("ix_perf_slow_request_at", "perf_slow_request", ["at"])

    if not _has("perf_server_snapshot"):
        op.create_table(
            "perf_server_snapshot",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("at", sa.DateTime(), nullable=False),
            sa.Column("host_cpu_percent", sa.Float(), nullable=False),
            sa.Column("host_memory_percent", sa.Float(), nullable=False),
            sa.Column("process_cpu_percent", sa.Float(), nullable=False),
            sa.Column("process_memory_mb", sa.Float(), nullable=False),
            sa.Column("cpu_count", sa.Integer(), nullable=False),
            sa.Column("threads", sa.Integer(), nullable=False),
            sa.Column("db_pool_in_use", sa.Integer(), nullable=True),
            sa.Column("db_pool_size", sa.Integer(), nullable=True),
            sa.Column("requests_in_flight", sa.Integer(), nullable=False, server_default="0"),
            *_timestamps(),
        )
        op.create_index("ix_perf_server_snapshot_at", "perf_server_snapshot", ["at"])


def downgrade() -> None:
    op.drop_index("ix_perf_server_snapshot_at", table_name="perf_server_snapshot")
    op.drop_table("perf_server_snapshot")
    op.drop_index("ix_perf_slow_request_at", table_name="perf_slow_request")
    op.drop_table("perf_slow_request")
    op.drop_index("ix_perf_minute_route_minute", table_name="perf_minute")
    op.drop_index("ix_perf_minute_minute", table_name="perf_minute")
    op.drop_table("perf_minute")
