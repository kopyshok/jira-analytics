import importlib.util
from pathlib import Path


class _FakeDialect:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeBind:
    def __init__(self, dialect_name: str) -> None:
        self.dialect = _FakeDialect(dialect_name)


class _FakeBatchAlter:
    def __init__(self, op_calls: list[tuple], table_name: str, recreate=None) -> None:
        self.op_calls = op_calls
        self.table_name = table_name
        self.recreate = recreate

    def __enter__(self):
        self.op_calls.append(("batch_enter", self.table_name, self.recreate))
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.op_calls.append(("batch_exit", self.table_name, self.recreate))

    def add_column(self, column) -> None:
        self.op_calls.append(("batch_add_column", self.table_name, column.name))

    def create_foreign_key(self, name, referent_table, local_cols, remote_cols, ondelete=None) -> None:
        self.op_calls.append(
            (
                "batch_create_foreign_key",
                self.table_name,
                name,
                referent_table,
                tuple(local_cols),
                tuple(remote_cols),
                ondelete,
            )
        )

    def create_unique_constraint(self, name, columns) -> None:
        self.op_calls.append(("batch_create_unique_constraint", self.table_name, name, tuple(columns)))

    def drop_constraint(self, name, type_=None) -> None:
        self.op_calls.append(("batch_drop_constraint", self.table_name, name, type_))

    def drop_column(self, name) -> None:
        self.op_calls.append(("batch_drop_column", self.table_name, name))


class _FakeOp:
    def __init__(self, dialect_name: str) -> None:
        self.bind = _FakeBind(dialect_name)
        self.calls: list[tuple] = []

    def get_bind(self) -> _FakeBind:
        return self.bind

    def batch_alter_table(self, table_name: str, recreate=None) -> _FakeBatchAlter:
        self.calls.append(("batch_alter_table", table_name, recreate))
        return _FakeBatchAlter(self.calls, table_name, recreate)

    def create_foreign_key(
        self,
        name,
        source_table,
        referent_table,
        local_cols,
        remote_cols,
        ondelete=None,
    ) -> None:
        self.calls.append(
            (
                "create_foreign_key",
                name,
                source_table,
                referent_table,
                tuple(local_cols),
                tuple(remote_cols),
                ondelete,
            )
        )

    def drop_constraint(self, name, table_name=None, type_=None) -> None:
        self.calls.append(("drop_constraint", name, table_name, type_))

    def create_table(self, *args, **kwargs) -> None:
        self.calls.append(("create_table", args[0]))

    def create_index(self, *args, **kwargs) -> None:
        self.calls.append(("create_index", args[0]))

    def drop_table(self, *args, **kwargs) -> None:
        self.calls.append(("drop_table", args[0]))

    def drop_index(self, *args, **kwargs) -> None:
        self.calls.append(("drop_index", args[0]))


def _load_migration_module():
    repo_root = Path(__file__).resolve().parents[1]
    path = repo_root / "alembic" / "versions" / "043_scenario_snapshot_redesign.py"
    spec = importlib.util.spec_from_file_location("migration_043_scenario_snapshot_redesign", path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_upgrade_on_postgresql_adds_fks_without_recreating_scenario_revisions() -> None:
    module = _load_migration_module()
    fake_op = _FakeOp("postgresql")
    module.op = fake_op

    module.upgrade()

    assert (
        "batch_alter_table",
        "scenario_revisions",
        "always",
    ) not in fake_op.calls
    assert (
        "create_foreign_key",
        "fk_scenario_revisions_parent",
        "scenario_revisions",
        "scenario_revisions",
        ("parent_revision_id",),
        ("id",),
        "SET NULL",
    ) in fake_op.calls
    assert (
        "create_foreign_key",
        "fk_scenario_revisions_user",
        "scenario_revisions",
        "users",
        ("approved_by_user_id",),
        ("id",),
        "SET NULL",
    ) in fake_op.calls


def test_downgrade_on_postgresql_drops_fks_without_recreating_scenario_revisions() -> None:
    module = _load_migration_module()
    fake_op = _FakeOp("postgresql")
    module.op = fake_op

    module.downgrade()

    assert (
        "batch_alter_table",
        "scenario_revisions",
        "always",
    ) not in fake_op.calls
    assert (
        "drop_constraint",
        "fk_scenario_revisions_user",
        "scenario_revisions",
        "foreignkey",
    ) in fake_op.calls
    assert (
        "drop_constraint",
        "fk_scenario_revisions_parent",
        "scenario_revisions",
        "foreignkey",
    ) in fake_op.calls
