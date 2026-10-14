"""Применение переезда: одна транзакция, пересечения id, удаление по решениям, люди везде.

Плюс защита от повторного применения, цепочки id людей и часы задач,
которые остаются с облачными id.
"""
import json
from datetime import datetime, timedelta

import pytest

from app.models import (
    AppSetting,
    BacklogItem,
    CategoryMapping,
    Comment,
    Employee,
    Issue,
    IssueLink,
    KpiApproval,
    Project,
    ScopeProject,
    ScopeRoot,
    TeamDeskMark,
    User,
    Worklog,
)
from app.models.jira_migration import JiraMigrationReport
from app.services.jira_migration import apply as apply_module
from app.services.jira_migration import store
from app.services.jira_migration.apply import BLOCK_CLAIMED, ApplyRefused, apply_migration
from app.services.jira_migration.resolution import BLOCK_DONE
from app.services.jira_migration.state import (
    MIGRATION_STATE_KEY,
    STATE_DONE,
    STATE_PENDING,
    get_migration_state,
    is_sync_blocked,
    set_migration_state,
)
from app.services.plan_sources import Candidate, resolve_role
from tests.services.jira_migration.factory import make_issue, make_project, make_worklog
from tests.services.jira_migration.ready import seed_ready

NOW = datetime(2026, 10, 14, 12, 0)


@pytest.fixture
def ready(db_session):
    return seed_ready(db_session, NOW - timedelta(hours=1))


def _issue_ids(db) -> dict[str, str]:
    return dict(db.query(Issue.key, Issue.jira_issue_id).all())


def _apply(db):
    return apply_migration(db, now=NOW, backup_confirmed=True)


def _state_value(db) -> str:
    return db.query(AppSetting.value).filter_by(key=MIGRATION_STATE_KEY).scalar()


def _assert_untouched(db, ready) -> None:
    ids = _issue_ids(db)
    assert ids["OS-91030"] == "683676"
    assert ids["PMD-19591"] == "258783"
    assert "OS-1" in ids
    assert db.query(Worklog).count() == 1
    assert db.query(Comment).count() == 1
    assert db.query(Employee.jira_account_id).filter_by(display_name="Иванов Иван").scalar() == "cloud-ivanov"
    assert db.get(Issue, ready["a"]).assignee_account_id == "cloud-ivanov"
    assert db.query(Project.jira_project_id).filter_by(key="OS").scalar() == "11029"
    assert db.query(AppSetting.value).filter_by(key="jira_team_field_id").scalar() == "customfield_11526"
    assert _state_value(db) == STATE_PENDING
    assert db.get(JiraMigrationReport, ready["report"]).applied_at is None


def test_refused_without_backup_tick(db_session, ready):
    with pytest.raises(ApplyRefused) as exc:
        apply_migration(db_session, now=NOW, backup_confirmed=False)

    assert "Отметьте, что свежая копия базы сделана" in exc.value.blockers
    _assert_untouched(db_session, ready)


def test_refused_with_unresolved_person(db_session, ready):
    store.set_decision(db_session, store.KIND_PERSON, ready["sidorov"], None, "Админ")

    with pytest.raises(ApplyRefused) as exc:
        _apply(db_session)

    assert any("сотрудники — 1" in blocker for blocker in exc.value.blockers)
    _assert_untouched(db_session, ready)


def test_refused_when_stale_report(db_session):
    seed_ready(db_session, NOW - timedelta(hours=25))

    with pytest.raises(ApplyRefused) as exc:
        _apply(db_session)

    assert "Пробный прогон старше суток — запустите его заново" in exc.value.blockers
    assert _issue_ids(db_session)["OS-91030"] == "683676"


def test_refused_when_already_done(db_session, ready):
    set_migration_state(db_session, STATE_DONE)
    db_session.commit()

    with pytest.raises(ApplyRefused) as exc:
        _apply(db_session)

    assert exc.value.blockers == [BLOCK_DONE]
    assert _issue_ids(db_session)["OS-91030"] == "683676"


def test_second_apply_is_refused(db_session, ready):
    _apply(db_session)

    with pytest.raises(ApplyRefused) as exc:
        _apply(db_session)

    assert exc.value.blockers == [BLOCK_DONE]
    assert _issue_ids(db_session)["OS-91030"] == "258783"


def test_claimed_state_refuses_and_keeps_sync_blocked(db_session, ready):
    """Другое применение уже захватило переезд — второе отказывает, синк закрыт."""
    db_session.query(AppSetting).filter_by(key=MIGRATION_STATE_KEY).update({"value": "applying"})
    db_session.commit()

    with pytest.raises(ApplyRefused) as exc:
        _apply(db_session)

    assert exc.value.blockers == [BLOCK_CLAIMED]
    assert is_sync_blocked(db_session)
    assert _issue_ids(db_session)["OS-91030"] == "683676"
    assert db_session.query(Worklog).count() == 1


def test_concurrent_claim_between_checks_and_first_write(db_session, ready, monkeypatch):
    """Проверки прошли, но до первой записи переезд захватил другой запуск."""
    original = apply_module.collect_blockers

    def claimed_meanwhile(db, **kwargs):
        blockers = original(db, **kwargs)
        db.query(AppSetting).filter_by(key=MIGRATION_STATE_KEY).update({"value": "applying"})
        return blockers

    monkeypatch.setattr(apply_module, "collect_blockers", claimed_meanwhile)

    with pytest.raises(ApplyRefused) as exc:
        _apply(db_session)

    assert exc.value.blockers == [BLOCK_CLAIMED]
    _assert_untouched(db_session, ready)


def test_state_is_applying_inside_transaction(db_session, ready, monkeypatch):
    seen = {}
    original = apply_module._rebind_scope

    def spy(db, maps):
        seen["state"] = _state_value(db)
        seen["blocked"] = is_sync_blocked(db)
        return original(db, maps)

    monkeypatch.setattr(apply_module, "_rebind_scope", spy)

    _apply(db_session)

    assert seen == {"state": "applying", "blocked": True}
    assert _state_value(db_session) == STATE_DONE


def test_issue_ids_rebound_through_collision(db_session, ready):
    _apply(db_session)

    # OS-91030 получил id, который до переезда был у PMD-19591
    assert _issue_ids(db_session) == {
        "OS-91030": "258783", "PMD-19591": "999999", "OS-3": "cloud:500003", "OS-4": "500100",
    }


def test_many_issues_with_rotated_ids(db_session, ready):
    """Больше одной порции, и каждый новый id — старый id соседней задачи."""
    project = db_session.query(Project).filter_by(key="OS").one()
    total = 1203
    for n in range(total):
        make_issue(db_session, project, f"OS-{10000 + n}", str(800000 + n))
    row = db_session.get(JiraMigrationReport, ready["report"])
    maps = store.report_maps(row)
    maps["issues"].update({f"OS-{10000 + n}": str(800000 + (n + 1) % total) for n in range(total)})
    row.maps_json = json.dumps(maps)
    db_session.commit()

    summary = _apply(db_session)

    ids = _issue_ids(db_session)
    assert all(ids[f"OS-{10000 + n}"] == str(800000 + (n + 1) % total) for n in range(total))
    assert summary["issues_rebound"] == 3 + total


def test_issues_deleted_per_decisions_with_children_cleaned(db_session, ready):
    summary = _apply(db_session)

    assert summary["issues_deleted"] == 2
    assert db_session.get(Issue, ready["os4"]).parent_id is None
    assert db_session.query(BacklogItem).one().issue_id is None
    assert db_session.query(IssueLink).count() == 0
    assert db_session.query(TeamDeskMark).one().issue_id == ready["os3"]
    assert db_session.query(CategoryMapping).filter_by(entity_type="issue").count() == 0


def test_projects_and_scope_rebound(db_session, ready):
    _apply(db_session)

    assert dict(db_session.query(Project.key, Project.jira_project_id).all()) == {"OS": "10901", "PMD": "10902"}
    assert db_session.query(ScopeProject.jira_project_id).scalar() == "10901"
    assert db_session.query(ScopeRoot.jira_issue_id).scalar() == "258783"


def test_project_absent_in_new_jira_keeps_its_issues(db_session, ready):
    rfa = make_project(db_session, "RFA", "11999")
    make_issue(db_session, rfa, "RFA-1", "700001")
    db_session.commit()

    summary = _apply(db_session)

    assert db_session.query(Project.jira_project_id).filter_by(key="RFA").scalar() == "cloud:11999"
    assert _issue_ids(db_session)["RFA-1"] == "cloud:700001"
    assert summary["issues_deleted"] == 2


def test_people_rewritten_everywhere(db_session, ready):
    summary = _apply(db_session)

    employees = {e.display_name: (e.jira_account_id, e.jira_username) for e in db_session.query(Employee).all()}
    assert employees == {
        "Иванов Иван": ("JIRAUSER5", "Ivanov_I"),
        "Петров Пётр": ("JIRAUSER7", "Petrov_P"),
        "Сидоров Сидор": ("cloud:cloud-sidorov", None),
    }
    a = db_session.get(Issue, ready["a"])
    assert (a.assignee_account_id, a.reporter_account_id, a.developer_account_id) == (
        "JIRAUSER5", "JIRAUSER7", "cloud:cloud-sidorov",
    )
    assert db_session.get(Issue, ready["b"]).developer_account_id == "someone-else"
    assert db_session.query(BacklogItem.assignee_jira_account_at_choice).scalar() == "JIRAUSER5"
    assert db_session.get(User, ready["user"]).team_desk_filter["developers"] == [
        "cloud:cloud-sidorov", "unknown",
    ]
    payload = json.loads(db_session.query(KpiApproval).one().payload_json)
    assert payload["rows"][0]["account_id"] == "JIRAUSER5"
    assert (summary["employees_bound"], summary["employees_unbound"]) == (2, 1)
    assert summary["people_refs"] == {
        "issues_assignee": 1, "issues_reporter": 1, "issues_developer": 1,
        "backlog_assignee_at_choice": 1, "users_team_desk_filter": 1, "kpi_approvals": 1,
    }
    assert summary["kpi_payload_skipped"] == 0


def test_people_chain_rewritten_once(db_session, ready):
    """Новый ключ Иванова — старый id Петрова: X→Y и Y→Z не сливаются в X→Z."""
    store.set_decision(db_session, store.KIND_PERSON, ready["ivanov"],
                       {"action": "bind", "key": "cloud-petrov", "name": "Ivanov_I",
                        "display_name": "Иванов Иван"}, "Админ")

    _apply(db_session)

    employees = {e.display_name: e.jira_account_id for e in db_session.query(Employee).all()}
    assert employees["Иванов Иван"] == "cloud-petrov"
    assert employees["Петров Пётр"] == "JIRAUSER7"
    a = db_session.get(Issue, ready["a"])
    assert (a.assignee_account_id, a.reporter_account_id) == ("cloud-petrov", "JIRAUSER7")
    assert db_session.query(BacklogItem.assignee_jira_account_at_choice).scalar() == "cloud-petrov"
    payload = json.loads(db_session.query(KpiApproval).one().payload_json)
    assert payload["rows"][0]["account_id"] == "cloud-petrov"


def test_people_chain_split_across_batches(db_session):
    """Звенья цепочки далеко друг от друга в списке — всё равно одна перезапись на строку."""
    project = make_project(db_session, "OS", "11029")
    x = make_issue(db_session, project, "OS-1", "1", assignee_account_id="X")
    y = make_issue(db_session, project, "OS-2", "2", assignee_account_id="Y")
    other = make_issue(db_session, project, "OS-3", "3", assignee_account_id="p7")
    people_map = {"X": "Y"}
    people_map.update({f"p{n}": f"q{n}" for n in range(1200)})
    people_map["Y"] = "Z"

    rows = apply_module._remap_column(db_session, Issue, "assignee_account_id", people_map)
    db_session.commit()

    assert rows == 3
    assert db_session.get(Issue, x.id).assignee_account_id == "Y"
    assert db_session.get(Issue, y.id).assignee_account_id == "Z"
    assert db_session.get(Issue, other.id).assignee_account_id == "q7"


def test_malformed_kpi_payload_is_skipped(db_session, ready):
    db_session.add(KpiApproval(
        team="Команда Б", year=2026, quarter=3, approved_by="Админ", approved_at=NOW,
        payload_json="{не json",
    ))
    db_session.commit()

    summary = _apply(db_session)

    assert summary["kpi_payload_skipped"] == 1
    assert summary["people_refs"]["kpi_approvals"] == 1
    payloads = dict(db_session.query(KpiApproval.team, KpiApproval.payload_json).all())
    assert payloads["Команда Б"] == "{не json"
    assert json.loads(payloads["Команда А"])["rows"][0]["account_id"] == "JIRAUSER5"
    assert get_migration_state(db_session) == STATE_DONE


def test_plan_choice_still_valid(db_session, ready):
    summary = _apply(db_session)

    a = db_session.get(Issue, ready["a"])
    candidates = [Candidate(c["source"], c["label"], c["value"]) for c in a.planned_hours_sources["dev"]]
    assert [c.source for c in candidates] == ["customfield_11097", "customfield_11034"]
    resolution = resolve_role(candidates, a.planned_hours_choice["dev"])
    assert resolution.disputed is False
    assert resolution.value == 56.0
    assert summary["plan_sources"] == 1
    assert summary["choices_dropped"] == 0


def test_choice_on_unused_field_is_dropped_and_counted(db_session, ready):
    store.set_decision(db_session, store.KIND_FIELD, "customfield_14648", {"dc_field_id": None}, "Админ")

    summary = _apply(db_session)

    a = db_session.get(Issue, ready["a"])
    assert [c["source"] for c in a.planned_hours_sources["dev"]] == ["customfield_11097"]
    assert a.planned_hours_choice is None
    assert summary["choices_dropped"] == 1


def test_field_settings_rewritten_and_caches_dropped(db_session, ready):
    summary = _apply(db_session)

    settings = dict(db_session.query(AppSetting.key, AppSetting.value).all())
    assert settings["jira_team_field_id"] == "customfield_11092"
    assert settings["jira_sprint_field_id"] == "customfield_10109"
    assert json.loads(settings["jira_planned_dev_hours_field_id"]) == [
        {"field_id": "customfield_11097", "kind": "alt", "name": "Разработка (ч)"},
        {"field_id": "customfield_11034", "kind": "alt", "name": "Оценка 1С (ч)"},
    ]
    assert "jira_epic_link_field_id" not in settings
    assert summary["settings"] == 3


def test_worklogs_comments_deleted_and_state_done(db_session, ready):
    summary = _apply(db_session)

    assert db_session.query(Worklog).count() == 0
    assert db_session.query(Comment).count() == 0
    assert db_session.query(CategoryMapping).filter_by(entity_type="worklog").count() == 0
    assert (summary["worklogs_deleted"], summary["comments_deleted"]) == (1, 1)
    assert (summary["worklogs_kept"], summary["comments_kept"]) == (0, 0)
    assert get_migration_state(db_session) == STATE_DONE
    row = db_session.get(JiraMigrationReport, ready["report"])
    assert row.applied_at == NOW
    stored = json.loads(row.apply_summary_json)
    assert stored["issues_rebound"] == 3
    assert stored == summary


def test_hours_of_issues_keeping_cloud_ids_are_kept(db_session, ready):
    """Часы и комментарии задач, оставшихся с облачным id, не удаляются — id получают «cloud:»."""
    ivanov = db_session.get(Employee, ready["ivanov"])
    os2 = db_session.get(Issue, ready["os2"])
    os3 = db_session.get(Issue, ready["os3"])
    rfa = make_project(db_session, "RFA", "11999")
    rfa1 = make_issue(db_session, rfa, "RFA-1", "700001")
    make_worklog(db_session, os2, ivanov, datetime(2026, 9, 11, 10, 0), 1800, "770002")
    kept_os3 = make_worklog(db_session, os3, ivanov, datetime(2026, 9, 12, 10, 0), 7200, "770003")
    make_worklog(db_session, rfa1, ivanov, datetime(2026, 9, 13, 10, 0), 3600, "850609-rfa")
    db_session.add_all([
        Comment(jira_comment_id="c3", issue_id=os3.id, body="оставить", author_id=ivanov.id),
        Comment(jira_comment_id="c2", issue_id=os2.id, body="удалить", author_id=ivanov.id),
        CategoryMapping(entity_type="worklog", entity_id=kept_os3.id, category="dev"),
    ])
    db_session.commit()

    summary = _apply(db_session)

    worklogs = {w.jira_worklog_id: (w.issue_id, w.hours) for w in db_session.query(Worklog).all()}
    assert worklogs == {"cloud:770003": (os3.id, 2.0), "cloud:850609-rfa": (rfa1.id, 1.0)}
    assert dict(db_session.query(Comment.jira_comment_id, Comment.issue_id).all()) == {"cloud:c3": os3.id}
    assert db_session.query(CategoryMapping.entity_id).filter_by(entity_type="worklog").all() == [(kept_os3.id,)]
    assert (summary["worklogs_deleted"], summary["worklogs_kept"]) == (2, 2)
    assert (summary["comments_deleted"], summary["comments_kept"]) == (2, 1)


@pytest.mark.parametrize("step", ["_rewrite_people_refs", "_rebind_scope", "set_migration_state"])
def test_failure_rolls_everything_back(db_session, ready, monkeypatch, step):
    def broken(*args, **kwargs):
        raise RuntimeError("сбой посередине")

    monkeypatch.setattr(apply_module, step, broken)

    with pytest.raises(RuntimeError, match="сбой посередине"):
        _apply(db_session)

    _assert_untouched(db_session, ready)
