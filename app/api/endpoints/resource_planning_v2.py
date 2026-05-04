"""Resource Planning v2 endpoints — solver optimize + quality metric."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.plan_item_dependency import PlanItemDependency
from app.models.resource_plan import ResourcePlan
from app.models.resource_plan_assignment import ResourcePlanAssignment
from app.schemas.resource_planning_v2 import OptimizeResponse, QualityMetricSchema
from app.services.plan_quality_service import PlanQualityService
from app.services.pyjobshop_solver_service import PyJobShopSolverService

router = APIRouter()


@router.get("/{plan_id}/quality", response_model=QualityMetricSchema)
def get_plan_quality(plan_id: str, db: Session = Depends(get_db)) -> QualityMetricSchema:
    """Метрика качества плана: % перегрузок, просрочки, использование ёмкости."""
    try:
        metric = PlanQualityService(db).compute(plan_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return QualityMetricSchema(
        plan_id=metric["plan_id"],
        overload_days_pct=metric["overload_days_pct"],
        late_count=metric["late_count"],
        mean_utilization_pct=metric["mean_utilization_pct"],
        computed_at=datetime.now(timezone.utc),
    )


@router.post("/{plan_id}/optimize", response_model=OptimizeResponse)
def optimize_plan(plan_id: str, db: Session = Depends(get_db)) -> OptimizeResponse:
    """PyJobShop-оптимизация плана: создаёт форк с пересчитанными датами и исполнителями.

    Шаги:
    1. Вычисляет метрику качества «до».
    2. Запускает PyJobShopSolverService (до 30 с). При INFEASIBLE → 409.
    3. Клонирует план (форк) со всеми назначениями (включая is_pinned) и зависимостями.
    4. Применяет результат солвера к назначениям форка по phase-коду (не по индексу).
    5. Пинованные строки не перезаписываются (солвер их уже уважал; здесь — защитная проверка).
    6. Возвращает new_plan_id, before/after метрики, solver_status, solve_time_ms.
    """
    src = db.get(ResourcePlan, plan_id)
    if src is None:
        raise HTTPException(status_code=404, detail="ResourcePlan not found")

    # 1. Метрика «до»
    quality_svc = PlanQualityService(db)
    before_raw = quality_svc.compute(plan_id)
    before = QualityMetricSchema(
        plan_id=before_raw["plan_id"],
        overload_days_pct=before_raw["overload_days_pct"],
        late_count=before_raw["late_count"],
        mean_utilization_pct=before_raw["mean_utilization_pct"],
        computed_at=datetime.now(timezone.utc),
    )

    # 2. Запуск солвера
    result = PyJobShopSolverService(db).solve(plan_id)

    if result["solver_status"] == "INFEASIBLE":
        infeasible_sample = result["infeasible_items"][:5]
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Solver could not find a feasible schedule",
                "infeasible_items": infeasible_sample,
            },
        )

    # 3. Клонирование плана
    fork = ResourcePlan(
        scenario_id=src.scenario_id,
        team=src.team,
        quarter=src.quarter,
        year=src.year,
        status="ready",
        parent_plan_id=src.id,
        is_baseline=False,
        label="auto-PyJobShop",
    )
    db.add(fork)
    db.flush()  # fork.id теперь доступен

    # Клонируем назначения (включая is_pinned)
    src_assignments = list(
        db.scalars(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == src.id
            )
        )
    )
    fork_assignment_map: dict[str, ResourcePlanAssignment] = {}
    for a in src_assignments:
        fork_a = ResourcePlanAssignment(
            plan_id=fork.id,
            backlog_item_id=a.backlog_item_id,
            phase=a.phase,
            employee_id=a.employee_id,
            part_number=a.part_number,
            hours_allocated=a.hours_allocated,
            start_date=a.start_date,
            end_date=a.end_date,
            is_on_critical_path=a.is_on_critical_path,
            slack_days=a.slack_days,
            is_pinned=a.is_pinned,
        )
        db.add(fork_a)
        # Ключ: (backlog_item_id, phase) для последующего применения результата.
        # Если несколько строк с одинаковым (item, phase) — сохраняем первую;
        # solver также группирует по phase, поэтому соответствие однозначно.
        key = (a.backlog_item_id, a.phase)
        if key not in fork_assignment_map:
            fork_assignment_map[key] = fork_a

    # Клонируем зависимости
    src_deps = list(
        db.scalars(
            select(PlanItemDependency).where(PlanItemDependency.plan_id == src.id)
        )
    )
    for d in src_deps:
        db.add(
            PlanItemDependency(
                plan_id=fork.id,
                from_item_id=d.from_item_id,
                to_item_id=d.to_item_id,
                dep_type=d.dep_type,
                lag_days=d.lag_days,
                source=d.source,
            )
        )

    # 4. Применяем результат солвера к назначениям форка по phase-коду
    for solver_a in result["assignments"]:
        item_id = solver_a["backlog_item_id"]
        for phase_alloc in solver_a["phase_breakdown"]:
            phase = phase_alloc["phase"]
            fork_row = fork_assignment_map.get((item_id, phase))
            if fork_row is None:
                continue
            # 5. Пинованные строки не перезаписываем
            if fork_row.is_pinned:
                continue
            fork_row.start_date = phase_alloc["start_date"]
            fork_row.end_date = phase_alloc["end_date"]
            if phase_alloc["employee_id"] is not None:
                fork_row.employee_id = phase_alloc["employee_id"]

    db.commit()

    # 6. Метрика «после»
    after_raw = quality_svc.compute(fork.id)
    after = QualityMetricSchema(
        plan_id=after_raw["plan_id"],
        overload_days_pct=after_raw["overload_days_pct"],
        late_count=after_raw["late_count"],
        mean_utilization_pct=after_raw["mean_utilization_pct"],
        computed_at=datetime.now(timezone.utc),
    )

    return OptimizeResponse(
        new_plan_id=fork.id,
        before=before,
        after=after,
        solver_status=result["solver_status"],
        solve_time_ms=result["solve_time_ms"],
        infeasible_items=result["infeasible_items"],
    )
