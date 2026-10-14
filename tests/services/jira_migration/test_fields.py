"""Поля Jira при переезде: снимок облачных настроек, предложения, перезапись."""
import json

from app.models.app_setting import AppSetting
from app.services.jira_migration.cloud_fields import CLOUD_FIELD_NAMES
from app.services.jira_migration.fields import (
    build_field_rows,
    ensure_field_snapshot,
    load_field_snapshot,
    remap_plan_sources,
    resolve_fields,
    rewrite_setting_value,
    suggest_dc_field,
)
from app.services.plan_sources import (
    Candidate,
    FieldSpec,
    build_candidates,
    fingerprint,
    resolve_role,
)
from tests.dc_fixtures import load_dc

DC_FIELDS = [
    {"id": "customfield_11092", "name": "Продуктовая команда", "custom": True},
    {"id": "customfield_11097", "name": "Разработка (ч)", "custom": True},
    {"id": "customfield_11034", "name": "Оценка 1С (ч)", "custom": True},
    {"id": "customfield_11018", "name": "Окружение", "custom": True},
    {"id": "environment", "name": "Окружение", "custom": False},
    {"id": "priority", "name": "Приоритет", "custom": False},
    {"id": "duedate", "name": "Срок исполнения", "custom": False},
    {"id": "customfield_10109", "name": "Спринт", "custom": True},
    {"id": "customfield_20001", "name": "Дубль", "custom": True},
    {"id": "customfield_20002", "name": "дубль ", "custom": True},
]


def test_cloud_names_constant():
    assert len(CLOUD_FIELD_NAMES) == 35
    assert CLOUD_FIELD_NAMES["customfield_11526"] == "Продуктовая команда"
    assert CLOUD_FIELD_NAMES["priority"] == "Приоритет"
    # «1С» — кириллическая «С», как в облаке: иначе точное сравнение не сработает.
    assert CLOUD_FIELD_NAMES["customfield_14648"] == "Оценка 1С (ч)"
    assert CLOUD_FIELD_NAMES["customfield_14649"] == "Оценка QA 1С (ч)"


def test_snapshot_taken_once_and_kept(db_session):
    db_session.add_all([
        AppSetting(key="jira_team_field_id", value="customfield_11526"),
        AppSetting(key="jira_risk_field_id", value=""),
        AppSetting(key="jira_involvement_dev_field_id", value="customfield_12437"),
        AppSetting(key="jira_base_url", value="https://jira.example.test"),
    ])
    db_session.commit()

    assert ensure_field_snapshot(db_session) == {"jira_team_field_id": "customfield_11526"}

    db_session.query(AppSetting).filter_by(key="jira_team_field_id").one().value = "customfield_11092"
    db_session.commit()

    assert ensure_field_snapshot(db_session) == {"jira_team_field_id": "customfield_11526"}
    assert load_field_snapshot(db_session) == {"jira_team_field_id": "customfield_11526"}


def test_empty_snapshot_is_kept(db_session):
    """Первый прогон без настроек полей: пустой снимок не переснимается позже."""
    assert ensure_field_snapshot(db_session) == {}

    db_session.add(AppSetting(key="jira_team_field_id", value="customfield_11092"))
    db_session.commit()

    assert ensure_field_snapshot(db_session) == {}


def test_suggestion_by_exact_name_ignoring_case_and_edges():
    assert suggest_dc_field("customfield_11526", " продуктовая КОМАНДА ", DC_FIELDS) == {
        "id": "customfield_11092", "name": "Продуктовая команда",
    }
    assert suggest_dc_field("customfield_1", "Продуктовая", DC_FIELDS) is None  # без частичных


def test_repeated_name_resolved_by_kind_of_field():
    assert suggest_dc_field("customfield_11731", "Окружение", DC_FIELDS)["id"] == "customfield_11018"
    assert suggest_dc_field("environment", "Окружение", DC_FIELDS)["id"] == "environment"
    assert suggest_dc_field("customfield_3", "Дубль", DC_FIELDS) is None


def test_system_field_without_known_name_matched_by_id():
    assert suggest_dc_field("duedate", None, DC_FIELDS) == {"id": "duedate", "name": "Срок исполнения"}
    assert suggest_dc_field("customfield_99", None, DC_FIELDS) is None


def test_system_field_with_unmatched_name_falls_back_to_id():
    assert suggest_dc_field("priority", "Важность", DC_FIELDS) == {"id": "priority", "name": "Приоритет"}
    assert suggest_dc_field("customfield_99", "Нет такого", DC_FIELDS) is None


def test_rows_group_settings_by_cloud_field():
    snapshot = {
        "jira_team_field_id": "customfield_11526",
        "jira_impact_field_id": "priority",
        "jira_planned_dev_hours_field_id": json.dumps([
            {"field_id": "customfield_12432", "kind": "alt", "name": "Разработка (ч)"},
            {"field_id": "customfield_14648", "kind": "alt", "name": "Оценка 1С (ч)"},
        ], ensure_ascii=False),
        "jira_planned_qa_hours_field_id": "customfield_14648",
        "jira_sprint_field_id": "customfield_10019",
        "jira_epic_link_field_id": "customfield_77777",
    }
    rows = {r["cloud_id"]: r for r in build_field_rows(snapshot, DC_FIELDS)}

    assert set(rows) == {
        "customfield_11526", "priority", "customfield_12432", "customfield_14648",
        "customfield_10019", "customfield_77777",
    }
    assert rows["customfield_14648"]["settings"] == [
        "jira_planned_dev_hours_field_id", "jira_planned_qa_hours_field_id",
    ]
    assert rows["customfield_14648"]["suggested_id"] == "customfield_11034"
    assert rows["customfield_12432"]["suggested_name"] == "Разработка (ч)"
    assert rows["customfield_11526"]["labels"] == ["Команда задачи"]
    assert rows["customfield_10019"]["auto_only"] is True
    assert rows["customfield_77777"]["auto_only"] is True
    assert rows["customfield_77777"]["suggested_id"] is None
    assert rows["customfield_11526"]["auto_only"] is False


def test_resolution_uses_decisions_then_suggestions():
    rows = [
        {"cloud_id": "customfield_11526", "suggested_id": "customfield_11092", "auto_only": False},
        {"cloud_id": "customfield_12434", "suggested_id": None, "auto_only": False},
        {"cloud_id": "customfield_14649", "suggested_id": None, "auto_only": False},
        {"cloud_id": "customfield_77777", "suggested_id": None, "auto_only": True},
        {"cloud_id": "customfield_12432", "suggested_id": "customfield_11097", "auto_only": False},
    ]
    decisions = {
        "customfield_14649": {"dc_field_id": None},
        "customfield_12432": {"dc_field_id": "customfield_11034"},
    }
    res = resolve_fields(rows, decisions, DC_FIELDS)

    assert res.mapping == {
        "customfield_11526": "customfield_11092",
        "customfield_12434": None,
        "customfield_14649": None,
        "customfield_77777": None,
        "customfield_12432": "customfield_11034",
    }
    assert res.unresolved == ["customfield_12434"]
    assert res.names["customfield_11092"] == "Продуктовая команда"


def test_rewrite_plain_json_and_not_used():
    mapping = {"customfield_11526": "customfield_11092", "customfield_12432": "customfield_11097",
               "customfield_14648": None}
    names = {"customfield_11092": "Продуктовая команда", "customfield_11097": "Разработка (ч)"}

    assert rewrite_setting_value("customfield_11526", mapping, names) == "customfield_11092"
    assert rewrite_setting_value("customfield_14648", mapping, names) == ""
    raw = json.dumps([
        {"field_id": "customfield_12432", "kind": "sum", "name": "Разработка"},
        {"field_id": "customfield_14648", "kind": "alt", "name": "Оценка 1С (ч)"},
    ], ensure_ascii=False)
    assert json.loads(rewrite_setting_value(raw, mapping, names)) == [
        {"field_id": "customfield_11097", "kind": "sum", "name": "Разработка (ч)"},
    ]
    only_dropped = json.dumps([{"field_id": "customfield_14648", "kind": "alt", "name": "x"}])
    assert rewrite_setting_value(only_dropped, mapping, names) == ""


def test_plan_choice_stays_valid_after_remap():
    old = [Candidate("customfield_12432", "Разработка (ч)", 40.0),
           Candidate("customfield_14648", "Оценка 1С (ч)", 56.0)]
    sources = {"dev": [c.to_dict() for c in old]}
    choice = {"dev": {"source": "customfield_14648", "fingerprint": fingerprint(old)}}
    mapping = {"customfield_12432": "customfield_11097", "customfield_14648": "customfield_11034"}

    new_sources, new_choice, dropped = remap_plan_sources(sources, choice, mapping)

    assert dropped is False
    assert [c["source"] for c in new_sources["dev"]] == ["customfield_11097", "customfield_11034"]
    assert new_choice["dev"]["source"] == "customfield_11034"
    candidates = [Candidate(c["source"], c["label"], c["value"]) for c in new_sources["dev"]]
    resolution = resolve_role(candidates, new_choice["dev"])
    assert resolution.disputed is False
    assert resolution.value == 56.0


def test_stale_choice_is_not_revived():
    old = [Candidate("customfield_12432", "А", 40.0), Candidate("customfield_14648", "Б", 56.0)]
    sources = {"dev": [c.to_dict() for c in old]}
    choice = {"dev": {"source": "customfield_14648", "fingerprint": "устарел"}}

    _, new_choice, dropped = remap_plan_sources(sources, choice, {"customfield_14648": "customfield_11034"})

    assert new_choice == {"dev": {"source": "customfield_11034", "fingerprint": "устарел"}}
    assert dropped is False


def test_sum_and_manual_sources_untouched():
    sources = {"qa": [{"source": "sum", "label": "А + Б", "value": 10.0}]}
    choice = {"qa": {"source": "manual", "fingerprint": "x"}}
    new_sources, new_choice, dropped = remap_plan_sources(sources, choice, {"customfield_1": "customfield_2"})
    assert new_sources == sources
    assert new_choice == choice
    assert dropped is False
    assert remap_plan_sources(None, None, {}) == (None, None, False)


ABC = [Candidate("customfield_1", "А", 40.0), Candidate("customfield_2", "Б", 56.0),
       Candidate("customfield_3", "В", 70.0)]
ABC_MAP = {"customfield_1": "customfield_101", "customfield_2": "customfield_102", "customfield_3": None}


def test_dropped_field_leaves_candidates_and_keeps_valid_choice():
    """«Не использовать» убирает кандидата: выбор Б совпадает с тем, что соберёт следующий синк."""
    sources = {"dev": [c.to_dict() for c in ABC]}
    choice = {"dev": {"source": "customfield_2", "fingerprint": fingerprint(ABC)}}

    new_sources, new_choice, dropped = remap_plan_sources(sources, choice, ABC_MAP)

    assert dropped is False
    assert [c["source"] for c in new_sources["dev"]] == ["customfield_101", "customfield_102"]
    next_sync = build_candidates(
        [FieldSpec("customfield_101", name="А"), FieldSpec("customfield_102", name="Б")],
        {"customfield_101": 40.0, "customfield_102": 56.0},
    )
    assert new_choice["dev"] == {"source": "customfield_102", "fingerprint": fingerprint(next_sync)}
    resolution = resolve_role(next_sync, new_choice["dev"])
    assert resolution.disputed is False
    assert resolution.value == 56.0


def test_choice_of_dropped_field_is_removed_and_reported():
    sources = {"dev": [c.to_dict() for c in ABC]}
    choice = {"dev": {"source": "customfield_3", "fingerprint": fingerprint(ABC)}}

    new_sources, new_choice, dropped = remap_plan_sources(sources, choice, ABC_MAP)

    assert dropped is True
    assert new_choice is None
    assert [c["source"] for c in new_sources["dev"]] == ["customfield_101", "customfield_102"]

    # Устаревший выбор и так не действовал — удаляется, но сброшенным не считается.
    stale = {"dev": {"source": "customfield_3", "fingerprint": "устарел"}}
    assert remap_plan_sources(sources, stale, ABC_MAP)[1:] == (None, False)


def test_role_without_candidates_left_disappears():
    sources = {"qa": [{"source": "customfield_3", "label": "В", "value": 8.0}],
               "dev": [c.to_dict() for c in ABC[:1]]}

    new_sources, _, _ = remap_plan_sources(sources, None, ABC_MAP)

    assert new_sources == {"dev": [{"source": "customfield_101", "label": "А", "value": 40.0}]}
    assert remap_plan_sources(sources | {"dev": []}, None, ABC_MAP)[0] is None


def test_real_dc_fields_cover_known_cloud_names():
    dc_fields = [
        {"id": f["id"], "name": f["name"], "custom": bool(f.get("custom"))}
        for f in load_dc("fields.json")
    ]
    missing = {
        cid for cid, name in CLOUD_FIELD_NAMES.items()
        if suggest_dc_field(cid, name, dc_fields) is None
    }
    assert missing == {
        "customfield_12434", "customfield_12436", "customfield_12437",
        "customfield_12438", "customfield_12439", "customfield_14649",
    }
    assert suggest_dc_field("customfield_11526", "Продуктовая команда", dc_fields)["id"] == "customfield_11092"
    assert suggest_dc_field("customfield_11731", "Окружение", dc_fields)["id"] == "customfield_11018"
