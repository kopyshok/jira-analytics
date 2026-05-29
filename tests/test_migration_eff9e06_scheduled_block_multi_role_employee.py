import importlib.util
import types
from pathlib import Path


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeDialect:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeBind:
    def __init__(self, dialect_name: str, role_rows, employee_rows) -> None:
        self.dialect = _FakeDialect(dialect_name)
        self.role_rows = role_rows
        self.employee_rows = employee_rows
        self.calls = []

    def execute(self, statement, params=None):
        sql = str(statement)
        self.calls.append(sql)
        if "role_id" in sql and "employee_id" not in sql:
            return _FakeResult(self.role_rows)
        if "employee_id" in sql:
            return _FakeResult(self.employee_rows)
        return _FakeResult([])


class _FakeBatchAlter:
    def __init__(self, op_calls: list[tuple], table_name: str) -> None:
        self.op_calls = op_calls
        self.table_name = table_name

    def __enter__(self):
        self.op_calls.append(("batch_enter", self.table_name))
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.op_calls.append(("batch_exit", self.table_name))

    def drop_column(self, name) -> None:
        self.op_calls.append(("batch_drop_column", self.table_name, name))

    def add_column(self, column) -> None:
        self.op_calls.append(("batch_add_column", self.table_name, column.name))


class _FakeOp:
    def __init__(self, bind: _FakeBind) -> None:
        self.bind = bind
        self.calls: list[tuple] = []
        self.bulk_inserts: list[tuple[str, list[dict]]] = []

    def get_bind(self) -> _FakeBind:
        return self.bind

    def create_table(self, *args, **kwargs) -> None:
        self.calls.append(("create_table", args[0]))

    def create_index(self, *args, **kwargs) -> None:
        self.calls.append(("create_index", args[0]))

    def batch_alter_table(self, table_name: str):
        self.calls.append(("batch_alter_table", table_name))
        return _FakeBatchAlter(self.calls, table_name)

    def bulk_insert(self, table, rows) -> None:
        self.bulk_inserts.append((table.name, list(rows)))

    def execute(self, statement, params=None):
        self.calls.append(("op_execute", str(statement)))
        raise AssertionError("upgrade should not use raw SQL randomblob for id generation")

    def drop_index(self, *args, **kwargs) -> None:
        self.calls.append(("drop_index", args[0]))

    def drop_table(self, *args, **kwargs) -> None:
        self.calls.append(("drop_table", args[0]))


def _load_migration_module():
    repo_root = Path(__file__).resolve().parents[1]
    path = repo_root / "alembic" / "versions" / "eff9e06ce1f5_scheduled_block_multi_role_employee.py"
    spec = importlib.util.spec_from_file_location("migration_eff9e06", path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_upgrade_backfills_bridge_tables_without_sqlite_specific_randomblob() -> None:
    module = _load_migration_module()
    bind = _FakeBind(
        "postgresql",
        role_rows=[("block-1", "role-1")],
        employee_rows=[("block-2", "emp-1")],
    )
    fake_op = _FakeOp(bind)
    module.op = fake_op

    uuids = iter(["uuid-role", "uuid-employee"])
    module.uuid = types.SimpleNamespace(uuid4=lambda: next(uuids))

    module.upgrade()

    assert fake_op.bulk_inserts == [
        (
            "scheduled_block_role",
            [{"id": "uuid-role", "block_id": "block-1", "role_id": "role-1"}],
        ),
        (
            "scheduled_block_employee",
            [{"id": "uuid-employee", "block_id": "block-2", "employee_id": "emp-1"}],
        ),
    ]
    assert all("randomblob" not in call.lower() for call in bind.calls)
