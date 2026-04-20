"""Tests for CapacityService mandatory_percent_breakdown + mandatory_hours v3.

v3: available = effective_norm × productive_percent / 100; mandatory = effective_norm − available.
productive_percent = Σ правил для work_types, у которых есть хотя бы одна
привязанная категория (Category.work_type_id = wt.id).
"""

import pytest

from app.models import (
    Category,
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


@pytest.fixture
def productive_wt(db_session):
    """v3: productive work type + linked Category — без этого productive_pct = 0.

    Правила на этот wt тесты добавляют сами (role=None, % нужный каждому кейсу),
    чтобы получить нужное соотношение productive/mandatory.
    """
    wt = MandatoryWorkType(
        code="productive", label="Продуктив", is_active=True
    )
    db_session.add(wt)
    db_session.flush()
    db_session.add(
        Category(
            code="cat_productive",
            label="Productive",
            is_system=False,
            work_type_id=wt.id,
        )
    )
    db_session.flush()
    return wt


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
    """v3: available = effective_norm × productive_percent / 100; mandatory = rest."""

    def test_monthly_capacity_applies_quarter_rule(
        self, db_session, employee, work_types, productive_wt
    ):
        # 10% tech_debt + 5% org = 15% mandatory для Q1/programmer.
        # productive (связан с Category) = 85% → available = 85% * norm,
        # mandatory = norm − available = 15% * norm.
        db_session.add_all([
            RoleCapacityRule(
                year=2026, quarter=1, role="programmer",
                work_type_id=work_types["tech_debt"].id, percent_of_norm=10.0,
            ),
            RoleCapacityRule(
                year=2026, quarter=1, role="programmer",
                work_type_id=work_types["organizational"].id, percent_of_norm=5.0,
            ),
            RoleCapacityRule(
                year=2026, quarter=1, role=None,
                work_type_id=productive_wt.id, percent_of_norm=85.0,
            ),
        ])
        db_session.flush()

        svc = CapacityService(db_session)
        # Март 2026: 22 рабочих дня × 8 = 176 ч нормы.
        mc = svc.monthly_capacity(employee.id, 2026, 3)
        assert mc.norm_hours == 176.0
        assert mc.mandatory_hours == pytest.approx(176.0 * 0.15)
        assert mc.available_hours == pytest.approx(176.0 * 0.85)

    def test_no_productive_rule_no_available(self, db_session, work_types):
        """v3: без правил на productive work_type доступные часы = 0.

        В v2 «нет правил» означало mandatory=0 → available=norm. В v3 проценты
        описывают 100% времени, поэтому «нет productive правил» → productive_pct=0
        → available=0, а вся норма отправляется в mandatory.
        """
        emp = Employee(
            jira_account_id="acc-nul", display_name="NoRole",
            is_active=True, role=None,
        )
        db_session.add(emp)
        db_session.flush()
        # Правило на роль, которой нет у сотрудника — не применяется ни по роли,
        # ни по fallback (role=None). Категорий, привязанных к work_type, тоже нет.
        db_session.add(RoleCapacityRule(
            year=2026, quarter=1, role="programmer",
            work_type_id=work_types["tech_debt"].id, percent_of_norm=20.0,
        ))
        db_session.flush()

        svc = CapacityService(db_session)
        mc = svc.monthly_capacity(emp.id, 2026, 3)
        assert mc.available_hours == 0.0
        assert mc.mandatory_hours == mc.norm_hours

    def test_inactive_work_type_ignored(
        self, db_session, employee, work_types, productive_wt
    ):
        """Правила на деактивированный work_type не должны попадать в breakdown.

        productive_wt (100% fallback) обеспечивает бэйзлайн: available = norm,
        mandatory = 0. Если бы правило на inactive_type применилось — mandatory
        стал бы > 0.
        """
        db_session.add_all([
            RoleCapacityRule(
                year=2026, quarter=1, role="programmer",
                work_type_id=work_types["inactive_type"].id, percent_of_norm=50.0,
            ),
            RoleCapacityRule(
                year=2026, quarter=1, role=None,
                work_type_id=productive_wt.id, percent_of_norm=100.0,
            ),
        ])
        db_session.flush()

        mc = CapacityService(db_session).monthly_capacity(employee.id, 2026, 3)
        assert mc.mandatory_hours == 0.0
        assert mc.available_hours == mc.norm_hours
