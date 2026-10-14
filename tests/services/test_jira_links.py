"""Ссылки на задачи строятся от адреса Jira из настроек, а не от облачного домена."""
from app.models.app_setting import AppSetting
from app.services.plan_common import jira_browse_base, jira_url


def test_no_setting_no_link(db_session):
    assert jira_browse_base(db_session) == ""
    assert jira_url("OS-1", "") is None


def test_link_from_setting(db_session):
    db_session.add(AppSetting(key="jira_base_url", value="https://jira.example.test/"))
    db_session.commit()
    base = jira_browse_base(db_session)
    assert base == "https://jira.example.test/browse/"
    assert jira_url("OS-91030", base) == "https://jira.example.test/browse/OS-91030"
    assert jira_url(None, base) is None
