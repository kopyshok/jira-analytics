"""Alembic migration environment."""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, inspect, pool

from alembic import context

from app.database import Base
from app.config import get_settings

# Import all models so they are registered with Base.metadata
from app.models import (
    Employee,
    Project,
    Issue,
    Worklog,
    Comment,
    SyncState,
    ScopeProject,
    ScopeRoot,
    CategoryMapping,
    CategoryOverride,
    WorklogQualityRule,
    Absence,
    MandatoryWorkType,
    RoleCapacityRule,
    EmployeeCapacityOverride,
    BacklogItem,
    PlanningScenario,
    ScenarioAllocation,
)

config = context.config

# Override sqlalchemy.url with settings
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _ensure_alembic_version_column(connection) -> None:
    inspector = inspect(connection)
    if "alembic_version" not in inspector.get_table_names():
        connection.exec_driver_sql(
            "CREATE TABLE alembic_version (version_num VARCHAR(64) NOT NULL PRIMARY KEY)"
        )
        return
    columns = {column["name"]: column for column in inspector.get_columns("alembic_version")}
    version_column = columns.get("version_num")
    if version_column is None:
        return
    length = getattr(version_column["type"], "length", None)
    if length is not None and length < 64 and connection.dialect.name == "postgresql":
        connection.exec_driver_sql("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64)")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        _ensure_alembic_version_column(connection)
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # Required for SQLite ALTER TABLE
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
