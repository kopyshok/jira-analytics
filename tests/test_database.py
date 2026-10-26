"""Tests for database engine options."""

from app.database import _engine_kwargs


def test_sqlite_engine_options_include_thread_check():
    kwargs = _engine_kwargs("sqlite:///./data/test.db", echo=False)

    assert kwargs["connect_args"] == {"check_same_thread": False, "timeout": 30}
    assert kwargs["echo"] is False


def test_non_sqlite_engine_options_do_not_include_sqlite_connect_args():
    kwargs = _engine_kwargs("postgresql+psycopg://user:pass@localhost/db", echo=True)

    connect_args = kwargs["connect_args"]
    assert "check_same_thread" not in connect_args and "timeout" not in connect_args
    # Пределы ожидания: без них чужая блокировка строки держит запрос бесконечно (23.10.2026).
    assert "lock_timeout=" in connect_args["options"]
    assert "idle_in_transaction_session_timeout=" in connect_args["options"]
    assert kwargs["echo"] is True


def test_non_sqlite_engine_options_size_pool_and_pre_ping():
    kwargs = _engine_kwargs("postgresql+psycopg://user:pass@localhost/db", echo=False)

    assert kwargs["pool_pre_ping"] is True
    # 40 потоков threadpool FastAPI + фоновые job'ы: дефолтных 5+10 не хватает
    assert kwargs["pool_size"] + kwargs["max_overflow"] >= 40
