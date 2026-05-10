"""SQLAlchemy models."""

from app.models.base import TimestampMixin, SyncedMixin, generate_uuid
from app.models.employee import Employee
from app.models.employee_team import EmployeeTeam
from app.models.project import Project
from app.models.issue import Issue
from app.models.worklog import Worklog
from app.models.comment import Comment
from app.models.sync_state import SyncState
from app.models.scope_project import ScopeProject
from app.models.scope_root import ScopeRoot
from app.models.category_mapping import CategoryMapping
from app.models.category_override import CategoryOverride
from app.models.worklog_quality_rule import WorklogQualityRule
from app.models.absence import Absence
from app.models.absence_reason import AbsenceReason
from app.models.mandatory_work_type import MandatoryWorkType
from app.models.role_capacity_rule import RoleCapacityRule
from app.models.employee_capacity_override import EmployeeCapacityOverride
from app.models.backlog_item import BacklogItem
from app.models.planning_scenario import PlanningScenario
from app.models.project_ai_summary import ProjectAISummary
from app.models.scenario_allocation import ScenarioAllocation
from app.models.app_setting import AppSetting
from app.models.category import Category
from app.models.hierarchy_rule import HierarchyRule
from app.models.production_calendar_day import ProductionCalendarDay
from app.models.role import Role
from app.models.scenario_rule import ScenarioRule
from app.models.scenario_revision import ScenarioRevision
from app.models.scenario_revision_item import ScenarioRevisionItem
from app.models.scenario_capacity_snapshot import ScenarioCapacitySnapshot
from app.models.scenario_norm_snapshot import ScenarioNormSnapshot
from app.models.scenario_absence_snapshot import ScenarioAbsenceSnapshot
from app.models.scenario_team_snapshot import ScenarioTeamSnapshot
from app.models.scenario_calendar_snapshot import ScenarioCalendarSnapshot
from app.models.scenario_rules_snapshot import ScenarioRulesSnapshot
from app.models.scenario_allocation_snapshot import ScenarioAllocationSnapshot
from app.models.scenario_allocation_breakdown_snapshot import ScenarioAllocationBreakdownSnapshot
from app.models.scenario_dictionary_snapshot import ScenarioDictionarySnapshot
from app.models.sync_schedule import SyncSchedule
from app.models.sync_run import SyncRun
from app.models.user import User, UserRole  # noqa: F401
from app.models.scheduled_block import ScheduledBlock
from app.models.scheduled_block_role import ScheduledBlockRole
from app.models.scheduled_block_employee import ScheduledBlockEmployee
from app.models.resource_plan import ResourcePlan
from app.models.resource_plan_assignment import ResourcePlanAssignment
from app.models.plan_item_dependency import PlanItemDependency
from app.models.plan_conflict import PlanConflict
from app.models.phase_predecessor import PhasePredecessor
from app.models.confluence_page_cache import ConfluencePageCache
from app.models.theme import Theme
from app.models.issue_classification import IssueClassification
from app.models.work_type_report_snapshot import WorkTypeReportSnapshot
from app.models.work_type_report_layout import WorkTypeReportLayout
from app.models.executive_snapshot import ExecutiveSnapshot
from app.models.user_rp_preferences import UserRpPreferences

__all__ = [
    "TimestampMixin",
    "SyncedMixin",
    "generate_uuid",
    "Employee",
    "EmployeeTeam",
    "Project",
    "Issue",
    "Worklog",
    "Comment",
    "SyncState",
    "ScopeProject",
    "ScopeRoot",
    "CategoryMapping",
    "CategoryOverride",
    "WorklogQualityRule",
    "Absence",
    "AbsenceReason",
    "MandatoryWorkType",
    "RoleCapacityRule",
    "EmployeeCapacityOverride",
    "BacklogItem",
    "PlanningScenario",
    "ProjectAISummary",
    "ScenarioAllocation",
    "AppSetting",
    "Category",
    "HierarchyRule",
    "ProductionCalendarDay",
    "Role",
    "ScenarioRule",
    "ScenarioRevision",
    "ScenarioRevisionItem",
    "ScenarioCapacitySnapshot",
    "ScenarioNormSnapshot",
    "ScenarioAbsenceSnapshot",
    "ScenarioTeamSnapshot",
    "ScenarioCalendarSnapshot",
    "ScenarioRulesSnapshot",
    "ScenarioAllocationSnapshot",
    "ScenarioAllocationBreakdownSnapshot",
    "ScenarioDictionarySnapshot",
    "SyncSchedule",
    "SyncRun",
    "User",
    "UserRole",
    "ScheduledBlock",
    "ScheduledBlockRole",
    "ScheduledBlockEmployee",
    "ResourcePlan",
    "ResourcePlanAssignment",
    "PlanItemDependency",
    "PlanConflict",
    "PhasePredecessor",
    "ConfluencePageCache",
    "Theme",
    "IssueClassification",
    "WorkTypeReportSnapshot",
    "WorkTypeReportLayout",
    "ExecutiveSnapshot",
    "UserRpPreferences",
]
