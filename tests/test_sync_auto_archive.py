"""Автоархив синка: отменённая задача без ручной категории уходит в архив."""
from app.models.issue import Issue
from app.services.sync_service import _auto_archive_cancelled


def test_wont_do_goes_to_archive():
    issue = Issue(status="Won't Do", assigned_category=None, include_in_analysis=True)
    _auto_archive_cancelled(issue)
    assert (issue.category, issue.assigned_category, issue.include_in_analysis) == ("archive", "archive", False)
    assert issue.category_verified is True


def test_old_cancel_status_still_archived():
    issue = Issue(status="Отменено", assigned_category=None, include_in_analysis=True)
    _auto_archive_cancelled(issue)
    assert issue.category == "archive"


def test_manual_category_kept():
    issue = Issue(status="Won't Do", assigned_category="archive_target", category="archive_target")
    _auto_archive_cancelled(issue)
    assert issue.category == "archive_target"


def test_open_issue_untouched():
    issue = Issue(status="В РАБОТЕ", assigned_category=None, category="active")
    _auto_archive_cancelled(issue)
    assert issue.category == "active"
