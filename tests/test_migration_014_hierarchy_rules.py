import importlib.util
from pathlib import Path


class _FakeBind:
    def __init__(self) -> None:
        self.calls = []

    def execute(self, statement, params) -> None:
        self.calls.append((statement, params))


class _FakeOp:
    def __init__(self, bind: _FakeBind) -> None:
        self.bind = bind

    def create_table(self, *args, **kwargs) -> None:
        return None

    def create_index(self, *args, **kwargs) -> None:
        return None

    def get_bind(self) -> _FakeBind:
        return self.bind


def _load_migration_module():
    repo_root = Path(__file__).resolve().parents[1]
    path = repo_root / "alembic" / "versions" / "014_hierarchy_rules.py"
    spec = importlib.util.spec_from_file_location("migration_014_hierarchy_rules", path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_hierarchy_rule_seed_uses_boolean_params() -> None:
    module = _load_migration_module()
    bind = _FakeBind()
    fake_op = _FakeOp(bind)
    module.op = fake_op

    module.upgrade()

    assert bind.calls
    for statement, params in bind.calls:
        sql = str(statement)
        assert ":enabled" in sql
        assert " 1, " not in sql
        assert " 0, " not in sql
        assert isinstance(params["np"], bool)
        assert isinstance(params["ic"], bool)
        assert isinstance(params["enabled"], bool)
