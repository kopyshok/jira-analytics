"""ProjectSummaryService: enrich child_summaries + Confluence pages."""
from unittest.mock import patch, AsyncMock
import pytest

from app.services.confluence_service import FetchedPage


@pytest.mark.asyncio
async def test_build_epic_data_includes_child_extras_and_confluence(db_session):
    from app.models.project import Project
    from app.models.issue import Issue
    p = Project(jira_project_id="P1", key="PRJ", name="P")
    from app.models.app_setting import AppSetting
    db_session.add(AppSetting(key="confluence_base_url", value="https://confluence.example.test"))
    db_session.add(p); db_session.commit()
    epic = Issue(
        jira_issue_id="1", key="PRJ-1", summary="Эпик",
        description="См ТЗ https://confluence.example.test/pages/viewpage.action?pageId=12345",
        issue_type="Epic", status="In Progress",
        project_id=p.id, category="initiatives_in_progress",
    )
    db_session.add(epic); db_session.flush()  # flush to get epic.id
    child = Issue(
        jira_issue_id="2", key="PRJ-2", summary="Доработка",
        description="Описание ТЗ", goal_text="Цель", current_behavior="Сейчас не работает",
        issue_type="Task", status="Done",
        project_id=p.id, parent_id=epic.id,
    )
    db_session.add(child); db_session.commit()

    fake_pages = [FetchedPage(
        page_id="12345",
        source_url="https://confluence.example.test/pages/viewpage.action?pageId=12345",
        title="Полное ТЗ", body_text="Контент ТЗ из confluence",
    )]
    with patch(
        "app.services.project_summary_service.ConfluenceService"
    ) as mock_svc:
        mock_svc.return_value.fetch_pages = AsyncMock(return_value=fake_pages)
        from app.services.project_summary_service import ProjectSummaryService
        data = await ProjectSummaryService(db_session)._build_epic_data_async(epic)

    cs = data["child_summaries"]
    assert any(c["key"] == "PRJ-2" and c.get("description") == "Описание ТЗ" for c in cs)
    assert any(c.get("goal_text") == "Цель" for c in cs)
    assert any(c.get("current_behavior") == "Сейчас не работает" for c in cs)
    assert data["confluence_pages"][0]["title"] == "Полное ТЗ"
    assert "Контент ТЗ из confluence" in data["confluence_pages"][0]["body_text"]
    mock_svc.return_value.fetch_pages.assert_awaited_once_with(
        ["https://confluence.example.test/pages/viewpage.action?pageId=12345"]
    )
