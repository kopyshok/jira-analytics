"""ThemeDictionaryService: CRUD, merge, archive, version bumps."""
import pytest
from app.models.mandatory_work_type import MandatoryWorkType
from app.models.theme import Theme
from app.models.issue_classification import IssueClassification
from app.models.issue import Issue
from app.models.project import Project
from app.services.theme_dictionary_service import ThemeDictionaryService


@pytest.fixture
def wt(db_session):
    wt = MandatoryWorkType(code="support_consult", label="Сопр", sort_order=1)
    db_session.add(wt); db_session.commit()
    return wt


def test_create_theme_bumps_version(db_session, wt):
    svc = ThemeDictionaryService(db_session)
    v0 = wt.theme_dict_version
    t = svc.create_theme(work_type_id=wt.id, name="Ошибки обмена", description="...", color="#00c9c8")
    db_session.refresh(wt)
    assert t.id and t.name == "Ошибки обмена"
    assert wt.theme_dict_version == v0 + 1


def test_rename_theme_bumps_version(db_session, wt):
    svc = ThemeDictionaryService(db_session)
    t = svc.create_theme(work_type_id=wt.id, name="A")
    v_after_create = wt.theme_dict_version
    svc.update_theme(theme_id=t.id, name="B")
    db_session.refresh(wt)
    assert wt.theme_dict_version == v_after_create + 1


def test_archive_theme_bumps_version(db_session, wt):
    svc = ThemeDictionaryService(db_session)
    t = svc.create_theme(work_type_id=wt.id, name="A")
    v = wt.theme_dict_version
    svc.archive_theme(t.id)
    db_session.refresh(wt); db_session.refresh(t)
    assert t.is_archived is True
    assert wt.theme_dict_version == v + 1


def test_merge_theme_reassigns_classifications(db_session, wt):
    """Merge T_src into T_dst → classifications re-pointed, T_src archived."""
    svc = ThemeDictionaryService(db_session)
    proj = Project(jira_project_id="P1", key="PROJ", name="Proj")
    db_session.add(proj); db_session.commit()
    issue = Issue(jira_issue_id="i1", key="PROJ-1", summary="x", issue_type="Task", status="Open", project_id=proj.id)
    db_session.add(issue); db_session.commit()

    t_src = svc.create_theme(work_type_id=wt.id, name="Src")
    t_dst = svc.create_theme(work_type_id=wt.id, name="Dst")
    cls = IssueClassification(issue_id=issue.id, work_type_id=wt.id, theme_id=t_src.id, input_hash="h", dictionary_version=1)
    db_session.add(cls); db_session.commit()

    svc.merge_theme(src_id=t_src.id, dst_id=t_dst.id)
    db_session.refresh(cls); db_session.refresh(t_src)
    assert cls.theme_id == t_dst.id
    assert t_src.is_archived is True


def test_unique_name_per_work_type(db_session, wt):
    svc = ThemeDictionaryService(db_session)
    svc.create_theme(work_type_id=wt.id, name="Dup")
    with pytest.raises(ValueError, match="exists"):
        svc.create_theme(work_type_id=wt.id, name="Dup")


def test_list_active_excludes_archived(db_session, wt):
    svc = ThemeDictionaryService(db_session)
    a = svc.create_theme(work_type_id=wt.id, name="A")
    b = svc.create_theme(work_type_id=wt.id, name="B")
    svc.archive_theme(b.id)
    active = svc.list_active(wt.id)
    assert [t.id for t in active] == [a.id]


def test_restore_theme_bumps_version(db_session, wt):
    svc = ThemeDictionaryService(db_session)
    t = svc.create_theme(work_type_id=wt.id, name="A")
    svc.archive_theme(t.id)
    db_session.refresh(wt)
    v = wt.theme_dict_version
    svc.restore_theme(t.id)
    db_session.refresh(wt); db_session.refresh(t)
    assert t.is_archived is False
    assert wt.theme_dict_version == v + 1


def test_restore_active_theme_is_noop(db_session, wt):
    """Restoring an already-active theme should not bump version."""
    svc = ThemeDictionaryService(db_session)
    t = svc.create_theme(work_type_id=wt.id, name="A")
    db_session.refresh(wt)
    v = wt.theme_dict_version
    svc.restore_theme(t.id)
    db_session.refresh(wt)
    assert wt.theme_dict_version == v
