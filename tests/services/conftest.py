"""Общие фикстуры для тестов app/services/kpi."""
import pytest

from app.models.project import Project


@pytest.fixture
def sample_project(db_session):
    """Проект-затычка с ключом OS (в спеке KPI — «1С»)."""
    project = Project(jira_project_id="p-kpi-1", key="OS", name="1С")
    db_session.add(project)
    db_session.flush()
    return project
