import importlib.util
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "migrate_to_postgres.py"
    spec = importlib.util.spec_from_file_location("migrate_to_postgres", path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_order_rows_for_self_referencing_table_puts_parents_before_children() -> None:
    module = _load_module()

    rows = [
        {"id": "child", "parent_id": "parent", "summary": "child"},
        {"id": "parent", "parent_id": None, "summary": "parent"},
        {"id": "root", "parent_id": None, "summary": "root"},
        {"id": "grandchild", "parent_id": "child", "summary": "grandchild"},
    ]

    ordered = module._order_rows_for_self_referencing_table("issues", rows)

    ordered_ids = [row["id"] for row in ordered]
    assert ordered_ids.index("parent") < ordered_ids.index("child")
    assert ordered_ids.index("child") < ordered_ids.index("grandchild")


def test_order_rows_for_non_self_referencing_table_keeps_original_order() -> None:
    module = _load_module()

    rows = [
        {"id": "b", "issue_id": "2"},
        {"id": "a", "issue_id": "1"},
    ]

    ordered = module._order_rows_for_self_referencing_table("worklogs", rows)

    assert ordered == rows


def test_copy_table_orders_self_referencing_rows_across_batches() -> None:
    module = _load_module()
    issues = module.Base.metadata.tables["issues"]

    rows = [
        {"id": "child", "parent_id": "parent", "key": "C"},
        {"id": "parent", "parent_id": None, "key": "P"},
    ]

    module._count_rows = lambda engine, table: len(rows)

    class _FakeResult:
        def __iter__(self):
            return iter([type("R", (), {"_mapping": row})() for row in rows])

    class _FakeSourceConn:
        def execution_options(self, **kwargs):
            return self

        def execute(self, statement):
            return _FakeResult()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

    class _FakeSource:
        def connect(self):
            return _FakeSourceConn()

    inserted_batches = []

    def _fake_insert_batch(target, table, batch):
        inserted_batches.append([row["id"] for row in batch])

    module._insert_batch = _fake_insert_batch

    source_count, copied = module._copy_table(_FakeSource(), object(), issues, batch_size=1)

    assert source_count == 2
    assert copied == 2
    assert inserted_batches == [["parent"], ["child"]]
