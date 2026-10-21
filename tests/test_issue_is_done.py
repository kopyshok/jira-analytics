"""«Выполнено» — по категории статуса Jira: имена статусов у нас русские и меняются."""
from app.models.issue import Issue


def test_done_by_status_category():
    assert Issue(status="ГОТОВО", status_category="done").is_done is True
    assert Issue(status="Won't Do", status_category="done").is_done is True


def test_done_by_legacy_status_name():
    # Старые данные и тесты без категории: статус с именем Done.
    assert Issue(status="Done", status_category=None).is_done is True


def test_not_done():
    assert Issue(status="В РАБОТЕ", status_category="indeterminate").is_done is False
    assert Issue(status=None, status_category=None).is_done is False
