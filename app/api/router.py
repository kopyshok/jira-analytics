"""API router configuration."""

from fastapi import APIRouter

from app.api.endpoints import sync, scope, analytics, mapping, capacity

api_router = APIRouter()


@api_router.get("/")
async def root():
    """API root endpoint."""
    return {
        "message": "Jira Analytics API",
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "sync": "/api/v1/sync",
            "scope": "/api/v1/scope",
            "analytics": "/api/v1/analytics",
            "mapping": "/api/v1/mapping",
            "capacity": "/api/v1/capacity",
        },
    }


# Include routers
api_router.include_router(sync.router, prefix="/sync", tags=["sync"])
api_router.include_router(scope.router, prefix="/scope", tags=["scope"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(mapping.router, prefix="/mapping", tags=["mapping"])
api_router.include_router(capacity.router, prefix="/capacity", tags=["capacity"])

# Future:
# from app.api.endpoints import employees, projects, worklogs, analytics, planning
# api_router.include_router(employees.router, prefix="/employees", tags=["employees"])
# api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
# api_router.include_router(worklogs.router, prefix="/worklogs", tags=["worklogs"])
# api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
# api_router.include_router(planning.router, prefix="/planning", tags=["planning"])
