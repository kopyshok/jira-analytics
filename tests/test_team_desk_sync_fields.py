"""Извлечение полей «Разработчик» и «DEV est (ч)» из ответа Jira."""
from app.services.sync_service import _extract_user_field, _to_float


def test_extract_user_field_reads_display_name_and_account_id():
    extra = {
        "customfield_14052": {
            "accountId": "627b98a119b129006829829d",
            "displayName": "Пряничников Алексей",
        }
    }
    assert _extract_user_field(extra, "customfield_14052") == (
        "627b98a119b129006829829d",
        "Пряничников Алексей",
    )


def test_extract_user_field_handles_empty():
    assert _extract_user_field({}, "customfield_14052") == (None, None)
    assert _extract_user_field({"customfield_14052": None}, "customfield_14052") == (None, None)
    assert _extract_user_field({"customfield_14052": {}}, "customfield_14052") == (None, None)
    assert _extract_user_field({"customfield_14052": "строка"}, "customfield_14052") == (None, None)


def test_extract_user_field_without_configured_id():
    extra = {"customfield_14052": {"accountId": "a", "displayName": "b"}}
    assert _extract_user_field(extra, None) == (None, None)


def test_dev_est_parses_number():
    assert _to_float(16.0) == 16.0
    assert _to_float("8,5") == 8.5
    assert _to_float(None) is None
