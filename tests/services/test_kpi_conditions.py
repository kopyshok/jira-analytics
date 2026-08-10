"""Условия отбора превращаются в запрос к задачам."""
import json
from datetime import date, datetime

import pytest

from app.models.issue import Issue
from app.services.kpi.conditions import (
    ATTR_COLUMNS,
    ATTRIBUTE_CHOICES,
    ConditionError,
    ConditionSet,
    build_issue_query,
)


def _make_issue(db, project, **kw):
    defaults = dict(
        jira_issue_id=kw.pop("jid", "1"), key=kw.pop("key", "OS-1"), summary="s",
        issue_type="Задача", status="ГОТОВО", status_category="done",
        project_id=project.id,
    )
    defaults.update(kw)
    issue = Issue(**defaults)
    db.add(issue)
    return issue


def test_filters_by_project_type_resolution(db_session, sample_project):
    _make_issue(db_session, sample_project, jid="1", key="OS-1", issue_type="Баг",
                resolution="Готово", environment="PROD", reporter_account_id="acc-1",
                resolved_at=datetime(2026, 7, 10))
    _make_issue(db_session, sample_project, jid="2", key="OS-2", issue_type="Баг",
                resolution="Отменено", environment="PROD", reporter_account_id="acc-1",
                resolved_at=datetime(2026, 7, 11))
    db_session.commit()

    cs = ConditionSet.from_json(json.dumps({
        "unit": "issues", "person_field": "author", "period_window": "closed_in",
        "conditions": [
            {"attr": "issue_type", "op": "in", "value": ["Баг"]},
            {"attr": "resolution", "op": "in", "value": ["Готово"]},
            {"attr": "environment", "op": "eq", "value": "PROD"},
        ],
    }))
    q = build_issue_query(
        db_session, cs, account_id="acc-1",
        periods=[(date(2026, 7, 1), date(2026, 7, 31))],
        excluded_statuses=["Отменено"], teams=None,
    )
    keys = sorted(i.key for i in q.all())
    assert keys == ["OS-1"]


def test_field_filled_requires_all_fields(db_session, sample_project):
    _make_issue(db_session, sample_project, jid="3", key="OS-3", reporter_account_id="acc-1",
                resolution="Готово", resolved_at=datetime(2026, 7, 10),
                goal_text="цель", current_behavior="как сейчас", description="описание")
    _make_issue(db_session, sample_project, jid="4", key="OS-4", reporter_account_id="acc-1",
                resolution="Готово", resolved_at=datetime(2026, 7, 10),
                goal_text="цель", current_behavior=None, description="описание")
    db_session.commit()

    cs = ConditionSet.from_json(json.dumps({
        "unit": "issues", "person_field": "author", "period_window": "closed_in",
        "conditions": [{"attr": "field_filled", "op": "all",
                        "value": ["goal_text", "current_behavior", "description"]}],
    }))
    q = build_issue_query(db_session, cs, account_id="acc-1",
                          periods=[(date(2026, 7, 1), date(2026, 7, 31))],
                          excluded_statuses=[], teams=None)
    assert [i.key for i in q.all()] == ["OS-3"]


def test_field_filled_rejects_blank_only_value(db_session, sample_project):
    """BLOCKER важно-4: пробелы и переводы строк не считаются заполнением поля."""
    _make_issue(db_session, sample_project, jid="5", key="OS-5", reporter_account_id="acc-1",
                resolution="Готово", resolved_at=datetime(2026, 7, 10),
                goal_text="  \n  ", current_behavior="как сейчас", description="описание")
    db_session.commit()

    cs = ConditionSet.from_json(json.dumps({
        "unit": "issues", "person_field": "author", "period_window": "closed_in",
        "conditions": [{"attr": "field_filled", "op": "all",
                        "value": ["goal_text", "current_behavior", "description"]}],
    }))
    q = build_issue_query(db_session, cs, account_id="acc-1",
                          periods=[(date(2026, 7, 1), date(2026, 7, 31))],
                          excluded_statuses=[], teams=None)
    assert q.all() == []


class TestResolvedOnTimeIsDateOnly:
    """BLOCKER 1: сравнение даты резолюции с плановой датой — по датам, не по моментам."""

    def _issue(self, db, project, *, resolved_at, planned_end_date):
        issue = Issue(
            jira_issue_id="10", key="OS-10", summary="s", issue_type="ИТ-задача",
            status="ГОТОВО", status_category="done", project_id=project.id,
            reporter_account_id="acc-1", assignee_account_id="acc-1",
            resolution="Готово", resolved_at=resolved_at, planned_end_date=planned_end_date,
        )
        db.add(issue)
        db.commit()
        return issue

    def _query(self, db):
        cs = ConditionSet.from_json(json.dumps({
            "unit": "issues", "person_field": "assignee", "period_window": "closed_in",
            "conditions": [{"attr": "resolved_on_time", "op": "is_true"}],
        }))
        return build_issue_query(db, cs, account_id="acc-1",
                                 periods=[(date(2026, 7, 1), date(2026, 7, 31))],
                                 excluded_statuses=[], teams=None)

    def test_closed_same_day_as_plan_at_1500_counts_as_on_time(self, db_session, sample_project):
        self._issue(
            db_session, sample_project,
            resolved_at=datetime(2026, 7, 10, 15, 0),
            planned_end_date=datetime(2026, 7, 10, 0, 0),
        )
        assert self._query(db_session).count() == 1

    def test_closed_next_day_at_0030_counts_as_late(self, db_session, sample_project):
        self._issue(
            db_session, sample_project,
            resolved_at=datetime(2026, 7, 11, 0, 30),
            planned_end_date=datetime(2026, 7, 10, 0, 0),
        )
        assert self._query(db_session).count() == 0


class TestConditionValidation:
    """BLOCKER 2: опечатка в условии падает с понятной ошибкой, а не тихо ослабляет фильтр."""

    def test_unknown_attr_raises(self):
        with pytest.raises(ConditionError, match="атрибут"):
            ConditionSet.from_json(json.dumps({
                "conditions": [{"attr": "environmentt", "op": "eq", "value": "PROD"}],
            }))

    def test_unknown_op_raises(self):
        with pytest.raises(ConditionError, match="сравнение"):
            ConditionSet.from_json(json.dumps({
                "conditions": [{"attr": "environment", "op": "eqal", "value": "PROD"}],
            }))

    def test_unknown_field_filled_name_raises(self):
        with pytest.raises(ConditionError, match="заполненности"):
            ConditionSet.from_json(json.dumps({
                "conditions": [{"attr": "field_filled", "op": "all", "value": ["goal_txt"]}],
            }))

    def test_unknown_person_field_raises(self):
        with pytest.raises(ConditionError, match="кто считается"):
            ConditionSet.from_json(json.dumps({"person_field": "autor", "conditions": []}))

    def test_unknown_period_window_raises(self):
        with pytest.raises(ConditionError, match="окно периода"):
            ConditionSet.from_json(json.dumps({"period_window": "closed", "conditions": []}))

    def test_unknown_unit_raises(self):
        with pytest.raises(ConditionError, match="единиц"):
            ConditionSet.from_json(json.dumps({"unit": "issue", "conditions": []}))


class TestDirectionNotInMetricAttributes:
    """Направление — фильтр отчёта, а не атрибут условия метрики (спека, раздел 6):
    иначе руководитель может зашить его в метрику, и переключатель направления
    на ведомости молча перестанет действовать на неё."""

    def test_direction_not_offered_as_condition_attribute(self):
        assert "direction" not in {c["key"] for c in ATTRIBUTE_CHOICES}

    def test_direction_column_still_available_for_report_filter(self):
        assert "direction" in ATTR_COLUMNS


class TestNullSafeExclusion:
    """Мелочь: ne/not_in на пустом значении не должны выбрасывать задачу из выборки."""

    def test_not_in_keeps_issue_with_null_direction(self, db_session, sample_project):
        _make_issue(db_session, sample_project, jid="6", key="OS-6", reporter_account_id="acc-1",
                    resolution="Готово", resolved_at=datetime(2026, 7, 10), direction=None)
        db_session.commit()

        cs = ConditionSet.from_json(json.dumps({
            "unit": "issues", "person_field": "author", "period_window": "closed_in",
            "conditions": [{"attr": "direction", "op": "not_in", "value": ["Прочее"]}],
        }))
        q = build_issue_query(db_session, cs, account_id="acc-1",
                              periods=[(date(2026, 7, 1), date(2026, 7, 31))],
                              excluded_statuses=[], teams=None)
        assert [i.key for i in q.all()] == ["OS-6"]


class TestCreatedAndClosedInWindow:
    """ВАЖНО 9: окно created_and_closed_in требует и создания, и закрытия в периоде."""

    def _cs(self):
        return ConditionSet.from_json(json.dumps({
            "unit": "issues", "person_field": "author", "period_window": "created_and_closed_in",
            "conditions": [],
        }))

    def test_created_before_period_excluded_even_if_closed_in_period(self, db_session, sample_project):
        _make_issue(db_session, sample_project, jid="9", key="OS-9", reporter_account_id="acc-1",
                    resolution="Готово", resolved_at=datetime(2026, 7, 10),
                    jira_created_at=datetime(2026, 6, 20))
        db_session.commit()

        q = build_issue_query(db_session, self._cs(), account_id="acc-1",
                              periods=[(date(2026, 7, 1), date(2026, 7, 31))],
                              excluded_statuses=[], teams=None)
        assert q.all() == []

    def test_created_and_closed_in_period_included(self, db_session, sample_project):
        _make_issue(db_session, sample_project, jid="10", key="OS-10a", reporter_account_id="acc-1",
                    resolution="Готово", resolved_at=datetime(2026, 7, 10),
                    jira_created_at=datetime(2026, 7, 2))
        db_session.commit()

        q = build_issue_query(db_session, self._cs(), account_id="acc-1",
                              periods=[(date(2026, 7, 1), date(2026, 7, 31))],
                              excluded_statuses=[], teams=None)
        assert [i.key for i in q.all()] == ["OS-10a"]


class TestOpenOrClosedInWindow:
    """Окно open_or_closed_in: закрытые в периоде + живые на его конец."""

    def _cs(self):
        return ConditionSet.from_json(json.dumps({
            "unit": "issues", "person_field": "author", "period_window": "open_or_closed_in",
            "conditions": [],
        }))

    def test_open_issue_created_before_period_included(self, db_session, sample_project):
        _make_issue(db_session, sample_project, jid="20", key="OS-20", reporter_account_id="acc-1",
                    status="В работе", resolution=None, resolved_at=None,
                    jira_created_at=datetime(2026, 5, 20))
        db_session.commit()

        q = build_issue_query(db_session, self._cs(), account_id="acc-1",
                              periods=[(date(2026, 7, 1), date(2026, 7, 31))],
                              excluded_statuses=[], teams=None)
        assert [i.key for i in q.all()] == ["OS-20"]

    def test_issue_created_after_period_excluded(self, db_session, sample_project):
        _make_issue(db_session, sample_project, jid="21", key="OS-21", reporter_account_id="acc-1",
                    status="В работе", resolution=None, resolved_at=None,
                    jira_created_at=datetime(2026, 8, 3))
        db_session.commit()

        q = build_issue_query(db_session, self._cs(), account_id="acc-1",
                              periods=[(date(2026, 7, 1), date(2026, 7, 31))],
                              excluded_statuses=[], teams=None)
        assert q.all() == []

    def test_issue_closed_before_period_excluded(self, db_session, sample_project):
        _make_issue(db_session, sample_project, jid="22", key="OS-22", reporter_account_id="acc-1",
                    resolution="Готово", resolved_at=datetime(2026, 6, 10),
                    jira_created_at=datetime(2026, 5, 1))
        db_session.commit()

        q = build_issue_query(db_session, self._cs(), account_id="acc-1",
                              periods=[(date(2026, 7, 1), date(2026, 7, 31))],
                              excluded_statuses=[], teams=None)
        assert q.all() == []

    def test_issue_closed_after_period_counts_as_open(self, db_session, sample_project):
        """Закрыта в августе — на конец июля была живой, значит в июль попадает."""
        _make_issue(db_session, sample_project, jid="23", key="OS-23", reporter_account_id="acc-1",
                    resolution="Готово", resolved_at=datetime(2026, 8, 5),
                    jira_created_at=datetime(2026, 6, 1))
        db_session.commit()

        q = build_issue_query(db_session, self._cs(), account_id="acc-1",
                              periods=[(date(2026, 7, 1), date(2026, 7, 31))],
                              excluded_statuses=[], teams=None)
        assert [i.key for i in q.all()] == ["OS-23"]


class TestExcludedStatusesTrimDenominator:
    """ВАЖНО 9: задача в исключённом статусе реально не попадает в выборку."""

    def test_cancelled_status_excluded(self, db_session, sample_project):
        _make_issue(db_session, sample_project, jid="11", key="OS-11", reporter_account_id="acc-1",
                    status="Отменено", resolution="Готово", resolved_at=datetime(2026, 7, 10))
        _make_issue(db_session, sample_project, jid="12", key="OS-12", reporter_account_id="acc-1",
                    status="ГОТОВО", resolution="Готово", resolved_at=datetime(2026, 7, 11))
        db_session.commit()

        cs = ConditionSet.from_json(json.dumps({
            "unit": "issues", "person_field": "author", "period_window": "closed_in",
            "conditions": [],
        }))
        q = build_issue_query(db_session, cs, account_id="acc-1",
                              periods=[(date(2026, 7, 1), date(2026, 7, 31))],
                              excluded_statuses=["Отменено"], teams=None)
        assert [i.key for i in q.all()] == ["OS-12"]


class TestMultiplePeriods:
    """Мелочь: несколько отрезков участия считаются по фактическим отрезкам, не по общему диапазону."""

    def test_issue_closed_in_gap_between_periods_excluded(self, db_session, sample_project):
        # Сотрудник состоял в команде 1-5 и 25-31 июля (ушёл и вернулся).
        # Задача закрыта 15 июля — внутри общего диапазона 1-31, но не
        # внутри ни одного из фактических отрезков.
        _make_issue(db_session, sample_project, jid="7", key="OS-7", reporter_account_id="acc-1",
                    resolution="Готово", resolved_at=datetime(2026, 7, 15))
        db_session.commit()

        cs = ConditionSet.from_json(json.dumps({
            "unit": "issues", "person_field": "author", "period_window": "closed_in",
            "conditions": [],
        }))
        q = build_issue_query(
            db_session, cs, account_id="acc-1",
            periods=[(date(2026, 7, 1), date(2026, 7, 5)), (date(2026, 7, 25), date(2026, 7, 31))],
            excluded_statuses=[], teams=None,
        )
        assert q.all() == []

    def test_issue_closed_inside_second_period_included(self, db_session, sample_project):
        _make_issue(db_session, sample_project, jid="8", key="OS-8", reporter_account_id="acc-1",
                    resolution="Готово", resolved_at=datetime(2026, 7, 27))
        db_session.commit()

        cs = ConditionSet.from_json(json.dumps({
            "unit": "issues", "person_field": "author", "period_window": "closed_in",
            "conditions": [],
        }))
        q = build_issue_query(
            db_session, cs, account_id="acc-1",
            periods=[(date(2026, 7, 1), date(2026, 7, 5)), (date(2026, 7, 25), date(2026, 7, 31))],
            excluded_statuses=[], teams=None,
        )
        assert [i.key for i in q.all()] == ["OS-8"]
