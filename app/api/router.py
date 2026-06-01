"""API router configuration."""

from fastapi import APIRouter, Depends

from app.api.endpoints import admin_release_notes as admin_release_notes_endpoints
from app.api.endpoints import admin_usage as admin_usage_endpoints
from app.api.endpoints import admin_users as admin_users_endpoints
from app.api.endpoints import ai_status as ai_status_endpoints
from app.api.endpoints import auth as auth_endpoints
from app.api.endpoints import llm as llm_endpoints
from app.api.endpoints import users as users_endpoints
from app.api.endpoints import release_notes as release_notes_endpoints
from app.api.endpoints import (
    analytics,
    backlog,
    capacity,
    capacity_rules,
    categories,
    employees,
    events as events_endpoints,
    executive as executive_endpoints,
    exports,
    feedback as feedback_endpoints,
    hierarchy_rules as hierarchy_rules_endpoints,
    issue_bulk,
    issue_config,
    mandatory_work_types,
    mapping,
    planning,
    production_calendar,
    projects,
    resource_planning,
    roles as roles_endpoints,
    scope,
    settings,
    sync,
    teams as teams_endpoints,
    themes as themes_endpoints,
    ui_config as ui_config_endpoints,
    usage as usage_endpoints,
    work_type_report as wtr_endpoints,
)
from app.core.auth_deps import get_current_user, require_admin

api_router = APIRouter()

# Authenticated business routers — every request must carry a valid JWT.
_auth_dep = [Depends(get_current_user)]
# Admin-only routers — JWT plus role=admin check.
_admin_dep = [Depends(require_admin)]


@api_router.get("/")
async def root():
    """API root endpoint."""
    return {
        "message": "Jira Analytics API",
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "employees": "/api/v1/employees",
            "projects": "/api/v1/projects",
            "sync": "/api/v1/sync",
            "scope": "/api/v1/scope",
            "analytics": "/api/v1/analytics",
            "mapping": "/api/v1/mapping",
            "capacity": "/api/v1/capacity",
            "backlog": "/api/v1/backlog",
            "planning": "/api/v1/planning",
            "exports": "/api/v1/exports",
            "settings": "/api/v1/settings",
            "categories": "/api/v1/categories",
        },
    }


# Public routers (no auth required by router-level dep). Login is open;
# /auth/me itself depends on get_current_user inside its own handler.
api_router.include_router(auth_endpoints.router, prefix="/auth", tags=["auth"])
api_router.include_router(users_endpoints.router, prefix="/users", tags=["users"])

# Authenticated business routers
api_router.include_router(
    employees.router, prefix="/employees", tags=["employees"], dependencies=_auth_dep,
)
api_router.include_router(
    projects.router, prefix="/projects", tags=["projects"], dependencies=_auth_dep,
)
api_router.include_router(
    teams_endpoints.router, prefix="/teams", tags=["teams"], dependencies=_auth_dep,
)
api_router.include_router(
    sync.router, prefix="/sync", tags=["sync"], dependencies=_auth_dep,
)
api_router.include_router(
    sync.jira_router, prefix="/jira", tags=["jira"], dependencies=_auth_dep,
)
api_router.include_router(
    scope.router, prefix="/scope", tags=["scope"], dependencies=_auth_dep,
)
api_router.include_router(
    analytics.router, prefix="/analytics", tags=["analytics"], dependencies=_auth_dep,
)
api_router.include_router(
    mapping.router, prefix="/mapping", tags=["mapping"], dependencies=_auth_dep,
)
api_router.include_router(
    capacity.router, prefix="/capacity", tags=["capacity"], dependencies=_auth_dep,
)
api_router.include_router(
    backlog.router, prefix="/backlog", tags=["backlog"], dependencies=_auth_dep,
)
api_router.include_router(
    planning.router, prefix="/planning", tags=["planning"], dependencies=_auth_dep,
)
api_router.include_router(
    exports.router, prefix="/exports", tags=["exports"], dependencies=_auth_dep,
)
api_router.include_router(
    categories.router, prefix="/categories", tags=["categories"], dependencies=_auth_dep,
)
api_router.include_router(
    issue_config.router, prefix="/issues", tags=["issues"], dependencies=_auth_dep,
)
api_router.include_router(
    issue_bulk.router, prefix="/issues", tags=["issues"], dependencies=_auth_dep,
)
api_router.include_router(
    production_calendar.router,
    prefix="/production-calendar",
    tags=["production_calendar"],
    dependencies=_auth_dep,
)
api_router.include_router(
    mandatory_work_types.router,
    prefix="/mandatory-work-types",
    tags=["mandatory-work-types"],
    dependencies=_auth_dep,
)
api_router.include_router(
    capacity_rules.role_rules_router,
    prefix="/capacity/role-rules",
    tags=["capacity-rules"],
    dependencies=_auth_dep,
)
api_router.include_router(
    capacity_rules.employee_overrides_router,
    prefix="/capacity/employee-overrides",
    tags=["capacity-rules"],
    dependencies=_auth_dep,
)
api_router.include_router(
    capacity_rules.absence_reasons_router,
    prefix="/capacity/absence-reasons",
    tags=["capacity-rules"],
    dependencies=_auth_dep,
)
api_router.include_router(
    roles_endpoints.router, prefix="/roles", tags=["roles"], dependencies=_auth_dep,
)
api_router.include_router(
    events_endpoints.router, prefix="/events", tags=["events"], dependencies=_auth_dep,
)
api_router.include_router(
    llm_endpoints.router, prefix="/llm", tags=["llm"], dependencies=_auth_dep,
)
api_router.include_router(
    ai_status_endpoints.router, prefix="/ai-status", tags=["ai-status"], dependencies=_auth_dep,
)
api_router.include_router(
    resource_planning.router,
    prefix="/resource-planning",
    tags=["resource-planning"],
    dependencies=_auth_dep,
)
api_router.include_router(
    themes_endpoints.router, prefix="/themes", tags=["themes"], dependencies=_auth_dep,
)
api_router.include_router(
    wtr_endpoints.router, prefix="/work-type-report", tags=["work-type-report"], dependencies=_auth_dep,
)
api_router.include_router(
    executive_endpoints.router, prefix="/executive", tags=["executive"], dependencies=_auth_dep,
)
api_router.include_router(
    ui_config_endpoints.router, prefix="/ui-config", tags=["ui-config"],
)
api_router.include_router(
    feedback_endpoints.router, prefix="/feedback", tags=["feedback"], dependencies=_auth_dep,
)
api_router.include_router(
    usage_endpoints.router, prefix="/usage", tags=["usage"], dependencies=_auth_dep,
)
api_router.include_router(
    release_notes_endpoints.router,
    prefix="/release-notes",
    tags=["release-notes"],
    dependencies=_auth_dep,
)

# Admin-only routers
api_router.include_router(
    admin_users_endpoints.router,
    prefix="/admin/users",
    tags=["admin"],
    dependencies=_admin_dep,
)
api_router.include_router(
    settings.router, prefix="/settings", tags=["settings"], dependencies=_admin_dep,
)
api_router.include_router(
    hierarchy_rules_endpoints.router,
    prefix="/hierarchy-rules",
    tags=["hierarchy-rules"],
    dependencies=_admin_dep,
)
api_router.include_router(
    admin_usage_endpoints.router,
    prefix="/admin/usage",
    tags=["admin-usage"],
    dependencies=_admin_dep,
)
api_router.include_router(
    admin_release_notes_endpoints.router,
    prefix="/admin/release-notes",
    tags=["release-notes-admin"],
    dependencies=_admin_dep,
)
