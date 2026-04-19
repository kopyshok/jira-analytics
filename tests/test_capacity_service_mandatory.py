"""Tests for CapacityService mandatory_percent_breakdown + mandatory_hours v2."""

import pytest

from app.models import (
    Employee,
    EmployeeCapacityOverride,
    MandatoryWorkType,
    RoleCapacityRule,
)
from app.services.capacity_service import CapacityService


@pytest.fixture
def employee(db_session):
    emp = Employee(
        jira_account_id="acc-dev",
        display_name="Dev",
        is_active=True,
        role="programmer",
    )
    db_session.add(emp)
    db_session.flush()
    return emp


@pytest.fixture
def work_types(db_session):
    wts = [
        MandatoryWorkType(code="tech_debt", label="Тех. долг", is_active=True),
        MandatoryWorkType(code="organizational", label="Орг.", is_active=True),
        MandatoryWorkType(code="inactive_type", label="Inactive", is_active=False),
    ]
    db_session.add_all(wts)
    db_session.flush()
    return {wt.code: wt for wt in wts}


class TestMandatoryPercentBreakdown:
    def test_empty_returns_zero_for_each_active(self, db_session, employee, work_types):
        svc = CapacityService(db_session)
        breakdown = svc.mandatory_percent_breakdown(employee, 2026, 1)
        assert breakdown == {"tech_debt": 0.0, "organizational": 0.0}
        assert "inactive_type" not in breakdown

    def test_role_rule_applied(self, db_session, employee, work_types):
        db_session.add(RoleCapacityRule(
            year=2026, quarter=1, role="programmer",
            work_type_id=work_types["tech_debt"].id, percent_of_norm=15.0,
        ))
        db_session.flush()

        breakdown = CapacityService(db_session).mandatory_percent_breakdown(
            employee, 2026, 1,
        )
        assert breakdown["tech_debt"] == 15.0
        assert breakdown["organizational"] == 0.0

    def test_fallback_null_role_rule(self, db_session, employee, work_types):
        """Если нет правила на роль — применяется NULL-fallback."""
        db_session.add(RoleCapacityRule(
            year=2026, quarter=1, role=None,
            work_type_id=work_types["organizational"].id, percent_of_norm=5.0,
        ))
        db_session.flush()

        breakdown = CapacityService(db_session).mandatory_percent_breakdown(
            employee, 2026, 1,
        )
        assert breakdown["organizational"] == 5.0

    def test_role_rule_overrides_null_fallback(self, db_session, employee, work_types):
        db_session.add_all([
            RoleCapacityRule(
                year=2026, quarter=1, role=None,
                work_type_id=work_types["tech_debt"].id, percent_of_norm=5.0,
            ),
            RoleCapacityRule(
                year=2026, quarter=1, role="programmer",
                work_type_id=work_types["tech_debt"].id, percent_of_norm=15.0,
            ),
        ])
        db_session.flush()

        breakdown = CapacityService(db_session).mandatory_percent_breakdown(
            employee, 2026, 1,
        )
        assert breakdown["tech_debt"] == 15.0

    def test_employee_override_wins(self, db_session, employee, work_types):
        db_session.add_all([
            RoleCapacityRule(
                year=2026, quarter=1, role="programmer",
                work_type_id=work_types["tech_debt"].id, percent_of_norm=15.0,
            ),
            EmployeeCapacityOverride(
                year=2026, quarter=1, employee_id=employee.id,
                work_type_id=work_types["tech_debt"].id, percent_of_norm=30.0,
            ),
        ])
        db_session.flush()

        breakdown = CapacityService(db_session).mandatory_percent_breakdown(
            employee, 2026, 1,
        )
        assert breakdown["tech_debt"] == 30.0


class TestMandatoryHoursIntegration:
    """mandatory_hours = norm_hours × total_percent / 100."""

    def test_monthly_capacity_applies_quarter_rule(self, db_session, employee, work_types):
        # 10% tech_debt + 5% org = 15% суммарно для Q1/programmer.
        db_session.add_all([
            RoleCapacityRule(
                year=2026, quarter=1, role="programmer",
                work_type_id=work_types["tech_debt"].id, percent_of_norm=10.0,
            ),
            RoleCapacityRule(
                year=2026, quarter=1, role="programmer",
                work_type_id=work_types["organizational"].id, percent_of_norm=5.0,
            ),
        ])
        db_session.flush()

        svc = CapacityService(db_session)
        # Март 2026: 22 рабочих дня × 8 = 176 ч нормы.
        mc = svc.monthly_capacity(employee.id, 2026, 3)
        assert mc.norm_hours == 176.0
        assert mc.mandatory_hours == pytest.approx(176.0 * 0.15)
        assert mc.available_hours == pytest.approx(176.0 * 0.85)

    def test_no_role_no_rule_zero_mandatory(self, db_session, work_types):
        emp = Employee(
            jira_account_id="acc-nul", display_name="NoRole",
            is_active=True, role=None,
        )
        db_session.add(emp)
        db_session.flush()
        db_session.add(RoleCapacityRule(
            year=2026, quarter=1, role="programmer",
            work_type_id=work_types["tech_debt"].id, percent_of_norm=20.0,
        ))
        db_session.flush()

        svc = CapacityService(db_session)
        mc = svc.monthly_capacity(emp.id, 2026, 3)
        assert mc.mandatory_hours == 0.0  # no role-match, no fallback

    def test_inactive_work_type_ignored(self, db_session, employee, work_types):
        """Правила на деактивированный work_type не должны попадать в breakdown."""
        db_session.add(RoleCapacityRule(
            year=2026, quarter=1, role="programmer",
            work_type_id=work_types["inactive_type"].id, percent_of_norm=50.0,
        ))
        db_session.flush()

        mc = CapacityService(db_session).monthly_capacity(employee.id, 2026, 3)
        assert mc.mandatory_hours == 0.0
