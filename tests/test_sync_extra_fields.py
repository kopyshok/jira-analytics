import pytest
from app.services.sync_service import _extract_text_field


def test_extract_text_field_string():
    extra = {"customfield_99": "цель задачи"}
    assert _extract_text_field(extra, "customfield_99") == "цель задачи"


def test_extract_text_field_adf():
    extra = {"customfield_99": {"type": "doc", "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": "цель"}]}
    ]}}
    assert _extract_text_field(extra, "customfield_99") == "цель"


def test_extract_text_field_missing():
    assert _extract_text_field({}, "customfield_99") is None


def test_extract_text_field_empty_id():
    assert _extract_text_field({"customfield_99": "x"}, "") is None
