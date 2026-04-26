"""Tests for database engine options."""

from app.database import _engine_kwargs


def test_sqlite_engine_options_include_thread_check():
    kwargs = _engine_kwargs("sqlite:///./data/test.db", echo=False)

    assert kwargs["connect_args"] == {"check_same_thread": False}
    assert kwargs["echo"] is False


def test_non_sqlite_engine_options_do_not_include_sqlite_connect_args():
    kwargs = _engine_kwargs("postgresql+psycopg://user:pass@localhost/db", echo=True)

    assert "connect_args" not in kwargs
    assert kwargs["echo"] is True
