"""Executive dashboard endpoint.

GET  /executive/dashboard?year&quarter&teams[]    — return cached or 404
POST /executive/dashboard/build                   — recompute + LLM synth, return snapshot
"""
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth_deps import get_current_user
from app.database import get_db
from app.models.executive_snapshot import ExecutiveSnapshot
from app.models.user import User
from app.services.executive_dashboard_service import (
    ExecutiveDashboardService,
    team_set_hash,
)
from app.services.llm.base import ConfigurationError, get_llm_provider
from app.services.llm.executive_synthesizer import (
    PROMPT_VERSION as EXEC_PROMPT_VERSION,
    ExecutiveSynthesizer,
)

logger = logging.getLogger("jira_analytics.executive")
router = APIRouter()


class ExecutiveBuildRequest(BaseModel):
    year: int
    quarter: int = Field(ge=1, le=4)
    teams: list[str] = Field(default_factory=list)


class ExecutiveDashboardResponse(BaseModel):
    year: int
    quarter: int
    team_set: list[str]
    generated_at: datetime
    model_id: Optional[str]
    prompt_version: Optional[str]
    data: dict


def _make_response(snap: ExecutiveSnapshot) -> ExecutiveDashboardResponse:
    return ExecutiveDashboardResponse(
        year=snap.year,
        quarter=snap.quarter,
        team_set=json.loads(snap.team_set_json),
        generated_at=snap.generated_at,
        model_id=snap.model_id,
        prompt_version=snap.prompt_version,
        data=json.loads(snap.snapshot_data),
    )


@router.get("/dashboard", response_model=ExecutiveDashboardResponse)
def get_dashboard(
    year: int,
    quarter: int,
    teams: list[str] = Query(default_factory=list),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return cached snapshot. 404 if none built yet."""
    th = team_set_hash(teams)
    snap = db.execute(
        select(ExecutiveSnapshot).where(
            ExecutiveSnapshot.year == year,
            ExecutiveSnapshot.quarter == quarter,
            ExecutiveSnapshot.team_set_hash == th,
        )
    ).scalar_one_or_none()
    if not snap:
        raise HTTPException(status_code=404, detail="Snapshot not built yet")
    return _make_response(snap)


@router.post("/dashboard/build", response_model=ExecutiveDashboardResponse)
async def build_dashboard(
    payload: ExecutiveBuildRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Aggregate fresh + run LLM synthesis + persist snapshot."""
    svc = ExecutiveDashboardService(db)
    findings = svc.aggregate(year=payload.year, quarter=payload.quarter, teams=payload.teams)

    findings_dict = {
        "period": findings.period,
        "kpi": findings.kpi,
        "health_trend": findings.health_trend,
        "modules": findings.modules,
        "queue": findings.queue,
        "hours_by_type_trend": findings.hours_by_type_trend,
        "plan_fact_by_role": findings.plan_fact_by_role,
        "top_risks": findings.top_risks,
        "capacity_by_role": findings.capacity_by_role,
    }

    try:
        provider = get_llm_provider(db)
    except ConfigurationError as e:
        logger.warning("LLM provider not configured: %s", e)
        provider = None

    model_id: Optional[str] = None
    if provider is not None:
        synth = ExecutiveSynthesizer(provider)
        synthesis, meta = await synth.synthesize(findings_dict)
        findings_dict["ai_summary"] = {
            "improved": synthesis.improved,
            "risk": synthesis.risk,
            "action": synthesis.action,
            "is_fallback": synthesis.is_fallback,
        }
        model_id = meta.get("model")
    else:
        findings_dict["ai_summary"] = {
            "improved": "Провайдер LLM не настроен.",
            "risk": "AI-сводка недоступна.",
            "action": "Настройте провайдер в /settings.",
            "is_fallback": True,
        }

    th = team_set_hash(payload.teams)
    existing = db.execute(
        select(ExecutiveSnapshot).where(
            ExecutiveSnapshot.year == payload.year,
            ExecutiveSnapshot.quarter == payload.quarter,
            ExecutiveSnapshot.team_set_hash == th,
        )
    ).scalar_one_or_none()

    if existing:
        existing.snapshot_data = json.dumps(findings_dict, ensure_ascii=False)
        existing.team_set_json = json.dumps(payload.teams, ensure_ascii=False)
        existing.model_id = model_id
        existing.prompt_version = EXEC_PROMPT_VERSION
        existing.generated_at = datetime.utcnow()
        existing.created_by = current_user.id
        snap = existing
    else:
        snap = ExecutiveSnapshot(
            year=payload.year,
            quarter=payload.quarter,
            team_set_hash=th,
            team_set_json=json.dumps(payload.teams, ensure_ascii=False),
            snapshot_data=json.dumps(findings_dict, ensure_ascii=False),
            model_id=model_id,
            prompt_version=EXEC_PROMPT_VERSION,
            created_by=current_user.id,
        )
        db.add(snap)
    db.commit()
    db.refresh(snap)
    return _make_response(snap)
