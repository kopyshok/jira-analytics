"""API router configuration."""

from fastapi import APIRouter

from app.api.endpoints import (
    analytics,
    backlog,
    capacity,
    mapping,
    planning,
    scope,
    sync,
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
            "sync": "/api/v1/sync",
            "scope": "/api/v1/scope",
            "analytics": "/api/v1/analytics",
            "mapping": "/api/v1/mapping",
            "capacity": "/api/v1/capacity",
            "backlog": "/api/v1/backlog",
            "planning": "/api/v1/planning",
        },
    }


# Include routers
api_router.include_router(sync.router, prefix="/sync", tags=["sync"])
api_router.include_router(scope.router, prefix="/scope", tags=["scope"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(mapping.router, prefix="/mapping", tags=["mapping"])
api_router.include_router(capacity.router, prefix="/capacity", tags=["capacity"])
api_router.include_router(backlog.router, prefix="/backlog", tags=["backlog"])
api_router.include_router(planning.router, prefix="/planning", tags=["planning"])
