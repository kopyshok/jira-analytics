"""Строковые литералы JQL: экранирование обратного слэша и кавычки."""
from app.connectors.jql import jql_quote


def test_plain_value_in_quotes():
    assert jql_quote("Ivanov_I_I") == '"Ivanov_I_I"'


def test_quote_escaped():
    assert jql_quote('o"neil') == r'"o\"neil"'


def test_backslash_escaped_before_quote():
    assert jql_quote("dom\\user") == r'"dom\\user"'
    assert jql_quote('a\\"b') == r'"a\\\"b"'
