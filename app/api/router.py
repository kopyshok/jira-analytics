"""API router configuration."""

from fastapi import APIRouter

from app.api.endpoints import admin_users as admin_users_endpoints
from app.api.endpoints import auth as auth_endpoints
from app.api.endpoints import llm as llm_endpoints
from app.api.endpoints import users as users_endpoints
from app.api.endpoints import (
    absence_reasons,
    analytics,
    backlog,
    capacity,
    categories,
    employee_capacity_overrides,
    employees,
    events as events_endpoints,
    exports,
    hierarchy_rules as hierarchy_rules_endpoints,
    issue_config,
    mandatory_work_types,
    mapping,
    planning,
    production_calendar,
    projects,
    role_capacity_rules,
    roles as roles_endpoints,
    scope,
    settings,
    sync,
    teams as teams_endpoints,
)

api_router = APIRouter()


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


# Include routers
api_router.include_router(employees.router, prefix="/employees", tags=["employees"])
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(teams_endpoints.router, prefix="/teams", tags=["teams"])
api_router.include_router(sync.router, prefix="/sync", tags=["sync"])
api_router.include_router(sync.jira_router, prefix="/jira", tags=["jira"])
api_router.include_router(scope.router, prefix="/scope", tags=["scope"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(mapping.router, prefix="/mapping", tags=["mapping"])
api_router.include_router(capacity.router, prefix="/capacity", tags=["capacity"])
api_router.include_router(backlog.router, prefix="/backlog", tags=["backlog"])
api_router.include_router(planning.router, prefix="/planning", tags=["planning"])
api_router.include_router(exports.router, prefix="/exports", tags=["exports"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(categories.router, prefix="/categories", tags=["categories"])
api_router.include_router(issue_config.router, prefix="/issues", tags=["issues"])
api_router.include_router(
    hierarchy_rules_endpoints.router,
    prefix="/hierarchy-rules",
    tags=["hierarchy-rules"],
)
api_router.include_router(
    production_calendar.router,
    prefix="/production-calendar",
    tags=["production_calendar"],
)
api_router.include_router(
    mandatory_work_types.router,
    prefix="/mandatory-work-types",
    tags=["mandatory-work-types"],
)
api_router.include_router(
    role_capacity_rules.router,
    prefix="/capacity/role-rules",
    tags=["capacity-rules"],
)
api_router.include_router(
    employee_capacity_overrides.router,
    prefix="/capacity/employee-overrides",
    tags=["capacity-rules"],
)
api_router.include_router(
    absence_reasons.router,
    prefix="/capacity/absence-reasons",
    tags=["capacity-rules"],
)
api_router.include_router(roles_endpoints.router, prefix="/roles", tags=["roles"])
api_router.include_router(events_endpoints.router, prefix="/events", tags=["events"])
api_router.include_router(auth_endpoints.router, prefix="/auth", tags=["auth"])
api_router.include_router(users_endpoints.router, prefix="/users", tags=["users"])
api_router.include_router(admin_users_endpoints.router, prefix="/admin/users", tags=["admin"])
api_router.include_router(llm_endpoints.router, prefix="/llm", tags=["llm"])
