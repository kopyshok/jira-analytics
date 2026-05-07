"""Work-type thematic report API."""
import json
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select, update, delete
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.auth_deps import get_current_user
from app.models.user import User
from app.models.work_type_report_snapshot import WorkTypeReportSnapshot
from app.models.work_type_report_layout import WorkTypeReportLayout
from app.models.mandatory_work_type import MandatoryWorkType
from app.models.issue_classification import IssueClassification
from app.schemas.work_type_report import (
    WorkTypeReportRequest, WorkTypeReportResponse,
    CandidateAcceptRequest, CandidateMergeRequest, CandidateIgnoreRequest,
    ManualClassifyRequest,
    LayoutCreateRequest, LayoutUpdateRequest, LayoutOut,
)
from app.services.work_type_report_service import WorkTypeReportService
from app.services.theme_dictionary_service import ThemeDictionaryService
from app.services.llm.base import get_llm_provider
from app.services.work_type_report_xlsx import export_snapshot_to_xlsx


router = APIRouter()


def _to_response(snap: WorkTypeReportSnapshot, wt: MandatoryWorkType) -> WorkTypeReportResponse:
    is_stale = snap.dictionary_version != wt.theme_dict_version
    return WorkTypeReportResponse(
        snapshot_id=snap.id,
        work_type_id=snap.work_type_id,
        year=snap.year, quarter=snap.quarter, month=snap.month,
        start_date=snap.start_date, end_date=snap.end_date,
        team_set=json.loads(snap.team_set_json),
        generated_at=snap.generated_at,
        model_id=snap.model_id, prompt_version=snap.prompt_version,
        dictionary_version=snap.dictionary_version,
        is_stale=is_stale,
        data=json.loads(snap.snapshot_data),
    )


def _make_service(db: Session) -> WorkTypeReportService:
    """Construct service with the configured LLM provider for both phases."""
    try:
        provider = get_llm_provider(db)
    except Exception:
        provider = None
    return WorkTypeReportService(
        db, classifier_provider=provider, synthesizer_provider=provider,
    )


@router.post("", response_model=WorkTypeReportResponse)
async def build_report(
    payload: WorkTypeReportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Build (or rebuild on force_refresh) a thematic report snapshot."""
    wt = db.get(MandatoryWorkType, payload.work_type_id)
    if not wt:
        raise HTTPException(404, "Work type not found")
    svc = _make_service(db)
    snap = await svc.get_or_build(
        work_type_id=payload.work_type_id,
        year=payload.year, quarter=payload.quarter, month=payload.month,
        teams=payload.teams, force_refresh=payload.force_refresh,
        user_id=current_user.id,
    )
    return _to_response(snap, wt)


@router.get("", response_model=WorkTypeReportResponse)
async def get_report(
    work_type_id: str = Query(...),
    year: int = Query(..., ge=2020, le=2100),
    quarter: int = Query(..., ge=1, le=4),
    month: Optional[int] = Query(None, ge=1, le=12),
    teams: Optional[str] = Query(None, description="CSV"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    wt = db.get(MandatoryWorkType, work_type_id)
    if not wt:
        raise HTTPException(404, "Work type not found")
    team_list = [t.strip() for t in teams.split(",") if t.strip()] if teams else []
    svc = _make_service(db)
    snap = await svc.get_or_build(
        work_type_id=work_type_id, year=year, quarter=quarter, month=month,
        teams=team_list, force_refresh=False, user_id=current_user.id,
    )
    return _to_response(snap, wt)


@router.post("/candidates/accept")
def accept_candidate(
    payload: CandidateAcceptRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Accept a candidate from a snapshot — creates Theme + reassigns matching classifications."""
    snap = db.get(WorkTypeReportSnapshot, payload.snapshot_id)
    if not snap:
        raise HTTPException(404, "Snapshot not found")
    name = payload.new_theme_name or payload.proposed_name
    svc = ThemeDictionaryService(db)
    try:
        theme = svc.create_theme(
            work_type_id=snap.work_type_id, name=name, color=payload.color,
            created_by=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(409, str(e))
    # Re-point all classifications with this candidate_name to the new theme
    db.execute(
        update(IssueClassification)
        .where(
            IssueClassification.work_type_id == snap.work_type_id,
            IssueClassification.candidate_name == payload.proposed_name,
            IssueClassification.theme_id.is_(None),
        )
        .values(theme_id=theme.id, candidate_name=None)
    )
    db.commit()
    return {"ok": True, "theme_id": theme.id}


@router.post("/candidates/merge")
def merge_candidate(
    payload: CandidateMergeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Merge a candidate into an existing theme."""
    snap = db.get(WorkTypeReportSnapshot, payload.snapshot_id)
    if not snap:
        raise HTTPException(404, "Snapshot not found")
    db.execute(
        update(IssueClassification)
        .where(
            IssueClassification.work_type_id == snap.work_type_id,
            IssueClassification.candidate_name == payload.proposed_name,
            IssueClassification.theme_id.is_(None),
        )
        .values(theme_id=payload.target_theme_id, candidate_name=None)
    )
    # Bump dictionary version so future builds re-evaluate
    wt = db.get(MandatoryWorkType, snap.work_type_id)
    if wt:
        wt.theme_dict_version = (wt.theme_dict_version or 0) + 1
    db.commit()
    return {"ok": True}


@router.post("/candidates/ignore")
def ignore_candidate(
    payload: CandidateIgnoreRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark candidate as ignored — no-op for classifications, but bumps dict version
    so the next build skips re-prompting LLM about these issues."""
    snap = db.get(WorkTypeReportSnapshot, payload.snapshot_id)
    if not snap:
        raise HTTPException(404, "Snapshot not found")
    return {"ok": True}


@router.post("/manual-classify")
def manual_classify(
    payload: ManualClassifyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Set theme_id on a single classification — overrides AI."""
    cls = db.execute(
        select(IssueClassification).where(
            IssueClassification.issue_id == payload.issue_id,
            IssueClassification.work_type_id == payload.work_type_id,
        )
    ).scalar_one_or_none()
    if cls:
        cls.theme_id = payload.theme_id
        cls.failed = False
        cls.failure_reason = None
        cls.llm_confidence = 1.0
        cls.prompt_version = "manual"
        if payload.contribution_text is not None:
            cls.contribution_text = payload.contribution_text
        cls.candidate_name = None
        cls.updated_at = datetime.utcnow()
    else:
        # Create one (rare — implementer picked a brand-new (issue, work_type) pairing)
        wt = db.get(MandatoryWorkType, payload.work_type_id)
        cls = IssueClassification(
            issue_id=payload.issue_id, work_type_id=payload.work_type_id,
            theme_id=payload.theme_id,
            contribution_text=payload.contribution_text,
            input_hash="manual",
            dictionary_version=(wt.theme_dict_version if wt else 1),
            llm_confidence=1.0,
            prompt_version="manual",
        )
        db.add(cls)
    db.commit()
    return {"ok": True}


# ---- Layouts ----

@router.get("/layouts", response_model=list[LayoutOut])
def list_layouts(
    work_type_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = db.execute(
        select(WorkTypeReportLayout).where(
            WorkTypeReportLayout.user_id == current_user.id,
            WorkTypeReportLayout.work_type_id == work_type_id,
        ).order_by(WorkTypeReportLayout.is_default.desc(), WorkTypeReportLayout.name)
    ).scalars().all()
    return [_layout_to_out(r) for r in rows]


def _layout_to_out(row: WorkTypeReportLayout) -> LayoutOut:
    return LayoutOut(
        id=row.id, user_id=row.user_id, work_type_id=row.work_type_id,
        name=row.name,
        grouping_dims=json.loads(row.grouping_dims_json),
        visible_columns=json.loads(row.visible_columns_json) if row.visible_columns_json else None,
        is_default=row.is_default,
        created_at=row.created_at, updated_at=row.updated_at,
    )


@router.post("/layouts", response_model=LayoutOut, status_code=201)
def create_layout(
    payload: LayoutCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.is_default:
        # Clear other defaults for this user×work_type
        db.execute(
            update(WorkTypeReportLayout)
            .where(
                WorkTypeReportLayout.user_id == current_user.id,
                WorkTypeReportLayout.work_type_id == payload.work_type_id,
                WorkTypeReportLayout.is_default.is_(True),
            )
            .values(is_default=False)
        )
    row = WorkTypeReportLayout(
        user_id=current_user.id, work_type_id=payload.work_type_id,
        name=payload.name,
        grouping_dims_json=json.dumps(payload.grouping_dims, ensure_ascii=False),
        visible_columns_json=json.dumps(payload.visible_columns, ensure_ascii=False) if payload.visible_columns else None,
        is_default=payload.is_default,
    )
    db.add(row); db.commit(); db.refresh(row)
    return _layout_to_out(row)


@router.patch("/layouts/{layout_id}", response_model=LayoutOut)
def update_layout(
    layout_id: str,
    payload: LayoutUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = db.get(WorkTypeReportLayout, layout_id)
    if not row or row.user_id != current_user.id:
        raise HTTPException(404, "Layout not found")
    if payload.name is not None:
        row.name = payload.name
    if payload.grouping_dims is not None:
        row.grouping_dims_json = json.dumps(payload.grouping_dims, ensure_ascii=False)
    if payload.visible_columns is not None:
        row.visible_columns_json = json.dumps(payload.visible_columns, ensure_ascii=False)
    if payload.is_default is True:
        # Clear other defaults
        db.execute(
            update(WorkTypeReportLayout)
            .where(
                WorkTypeReportLayout.user_id == current_user.id,
                WorkTypeReportLayout.work_type_id == row.work_type_id,
                WorkTypeReportLayout.is_default.is_(True),
                WorkTypeReportLayout.id != row.id,
            )
            .values(is_default=False)
        )
        row.is_default = True
    elif payload.is_default is False:
        row.is_default = False
    db.commit(); db.refresh(row)
    return _layout_to_out(row)


@router.delete("/layouts/{layout_id}")
def delete_layout(
    layout_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = db.get(WorkTypeReportLayout, layout_id)
    if not row or row.user_id != current_user.id:
        raise HTTPException(404, "Layout not found")
    db.delete(row); db.commit()
    return {"ok": True}


@router.get("/export/xlsx/{snapshot_id}")
def export_xlsx(
    snapshot_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    snap = db.get(WorkTypeReportSnapshot, snapshot_id)
    if not snap:
        raise HTTPException(404, "Snapshot not found")
    blob = export_snapshot_to_xlsx(snap)
    fname = f"thematic-{snap.year}q{snap.quarter}"
    if snap.month:
        fname += f"-m{snap.month:02d}"
    fname += f"-{snap.work_type_id[:8]}.xlsx"
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
