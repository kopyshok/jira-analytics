"""WorkTypeReportService — оркестратор: Map → aggregate → Reduce → snapshot."""
import hashlib
import json
import logging
from collections import defaultdict
from datetime import date, datetime, time
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.mandatory_work_type import MandatoryWorkType
from app.models.theme import Theme
from app.models.issue import Issue
from app.models.issue_classification import IssueClassification
from app.models.work_type_report_snapshot import WorkTypeReportSnapshot
from app.models.worklog import Worklog
from app.models.employee import Employee
from app.models.category import Category
from app.services.theme_dictionary_service import ThemeDictionaryService
from app.services.work_type_outlier_detector import detect_outliers_for_theme
from app.services.llm.work_type_classifier import (
    WorkTypeClassifier,
    ClassifierProvider,
)
from app.services.llm.work_type_synthesizer import (
    WorkTypeSynthesizer,
    SynthesizerProvider,
    SynthesisOutput,
    PROMPT_VERSION as SYNTH_PROMPT_VERSION,
)

logger = logging.getLogger("jira_analytics.thematic")


def _team_set_hash(teams: list[str]) -> str:
    """md5 of sorted team list. Empty list → 'all'."""
    if not teams:
        return "all"
    return hashlib.md5("|".join(sorted(teams)).encode("utf-8")).hexdigest()[:32]


def _resolve_period(year: int, quarter: int, month: Optional[int]) -> tuple[date, date]:
    from calendar import monthrange
    if month:
        end_d = monthrange(year, month)[1]
        return date(year, month, 1), date(year, month, end_d)
    q_start = (quarter - 1) * 3 + 1
    end_m = q_start + 2
    return date(year, q_start, 1), date(year, end_m, monthrange(year, end_m)[1])


class WorkTypeReportService:
    def __init__(
        self,
        db: Session,
        classifier_provider: Optional[ClassifierProvider] = None,
        synthesizer_provider: Optional[SynthesizerProvider] = None,
    ) -> None:
        self.db = db
        self.classifier_provider = classifier_provider
        self.synthesizer_provider = synthesizer_provider

    async def get_or_build(
        self,
        *,
        work_type_id: str,
        year: int,
        quarter: int,
        month: Optional[int],
        teams: list[str],
        force_refresh: bool,
        user_id: Optional[str],
    ) -> WorkTypeReportSnapshot:
        wt = self.db.get(MandatoryWorkType, work_type_id)
        if not wt:
            raise ValueError(f"Work type {work_type_id} not found")
        team_hash = _team_set_hash(teams)
        existing = self._find_existing(work_type_id, year, quarter, month, team_hash)
        if existing and not force_refresh and self._is_fresh(existing, wt):
            return existing
        return await self._build(
            work_type_id=work_type_id,
            wt=wt,
            year=year,
            quarter=quarter,
            month=month,
            teams=teams,
            team_hash=team_hash,
            user_id=user_id,
            existing=existing,
        )

    def _find_existing(
        self,
        work_type_id: str,
        year: int,
        quarter: int,
        month: Optional[int],
        team_hash: str,
    ) -> Optional[WorkTypeReportSnapshot]:
        return self.db.execute(
            select(WorkTypeReportSnapshot).where(
                WorkTypeReportSnapshot.work_type_id == work_type_id,
                WorkTypeReportSnapshot.year == year,
                WorkTypeReportSnapshot.quarter == quarter,
                WorkTypeReportSnapshot.month == month,
                WorkTypeReportSnapshot.team_set_hash == team_hash,
            )
        ).scalar_one_or_none()

    def _is_fresh(self, snap: WorkTypeReportSnapshot, wt: MandatoryWorkType) -> bool:
        if snap.dictionary_version != wt.theme_dict_version:
            return False
        max_issue_updated = self.db.execute(
            select(func.max(Issue.updated_at)).where(
                Issue.updated_at >= snap.generated_at
            )
        ).scalar()
        return max_issue_updated is None or max_issue_updated <= snap.generated_at

    async def _build(
        self,
        *,
        work_type_id: str,
        wt: MandatoryWorkType,
        year: int,
        quarter: int,
        month: Optional[int],
        teams: list[str],
        team_hash: str,
        user_id: Optional[str],
        existing: Optional[WorkTypeReportSnapshot],
    ) -> WorkTypeReportSnapshot:
        start_d, end_d = _resolve_period(year, quarter, month)

        # 1. Scope
        issues = self._select_scope_issues(work_type_id, start_d, end_d, teams)
        themes = ThemeDictionaryService(self.db).list_active(work_type_id)

        # 2. Map phase — classify each issue
        classifications: dict[str, IssueClassification] = {}
        if self.classifier_provider:
            clf = WorkTypeClassifier(self.db, self.classifier_provider)
            for issue in issues:
                cls = await clf.classify_issue(
                    issue=issue,
                    work_type_id=work_type_id,
                    themes=themes,
                    period_start=start_d,
                    period_end=end_d,
                )
                classifications[issue.id] = cls

        # 3. Aggregate findings deterministically
        findings, manual_review, employee_names = self._aggregate_findings(
            issues=issues,
            classifications=classifications,
            themes=themes,
            start_d=start_d,
            end_d=end_d,
            teams=teams,
        )

        # 4. Reduce phase
        synth_meta: dict = {}
        if self.synthesizer_provider and findings["totals"]["tasks"] > 0:
            synth = WorkTypeSynthesizer(self.synthesizer_provider)
            synthesis, synth_meta = await synth.synthesize(
                findings, employee_names=employee_names
            )
        else:
            synthesis = SynthesisOutput(
                headline=(
                    f"Всего {findings['totals']['hours']} ч / "
                    f"{findings['totals']['tasks']} задач."
                ),
                is_fallback=True,
            )

        # 5. Build snapshot data
        data = self._build_snapshot_data(findings, synthesis, manual_review)

        # 6. Persist
        snap = existing or WorkTypeReportSnapshot(
            work_type_id=work_type_id,
            year=year,
            quarter=quarter,
            month=month,
            start_date=start_d,
            end_date=end_d,
            team_set_hash=team_hash,
            team_set_json=json.dumps(teams, ensure_ascii=False),
            snapshot_data="",
            dictionary_version=wt.theme_dict_version,
        )
        snap.snapshot_data = json.dumps(data, ensure_ascii=False)
        snap.dictionary_version = wt.theme_dict_version
        snap.team_set_json = json.dumps(teams, ensure_ascii=False)
        snap.start_date, snap.end_date = start_d, end_d
        snap.model_id = synth_meta.get("model")
        snap.prompt_version = SYNTH_PROMPT_VERSION
        snap.generated_at = datetime.utcnow()
        snap.created_by = user_id
        if not existing:
            self.db.add(snap)
        self.db.commit()
        self.db.refresh(snap)
        return snap

    def _select_scope_issues(
        self,
        work_type_id: str,
        start_d: date,
        end_d: date,
        teams: list[str],
    ) -> list[Issue]:
        """Issues with at least one worklog in period AND assigned_category in this work_type's categories."""
        cat_codes = list(
            self.db.execute(
                select(Category.code).where(Category.work_type_id == work_type_id)
            ).scalars().all()
        )
        if not cat_codes:
            return []

        end_dt = datetime.combine(end_d, time(23, 59, 59))
        q = (
            select(Issue).distinct()
            .join(Worklog, Worklog.issue_id == Issue.id)
            .where(
                Worklog.started_at >= datetime.combine(start_d, time.min),
                Worklog.started_at <= end_dt,
                Issue.assigned_category.in_(cat_codes),
            )
        )
        if teams:
            q = q.where(Issue.team.in_(teams))
        return list(self.db.execute(q).scalars().all())

    def _aggregate_findings(
        self,
        *,
        issues: list[Issue],
        classifications: dict[str, IssueClassification],
        themes: list[Theme],
        start_d: date,
        end_d: date,
        teams: list[str],
    ) -> tuple[dict, list[dict], set[str]]:
        """Deterministic aggregation per spec.

        Returns (findings, manual_review, employee_names).
        - findings: {totals, themes, candidates, outliers}
        - manual_review: list of {issue_id, key, summary, hours} for failed classifications
        - employee_names: set of display_names for faithfulness validator
        """
        issue_ids = [i.id for i in issues]
        worklog_rows = []
        if issue_ids:
            end_dt = datetime.combine(end_d, time(23, 59, 59))
            wl_q = (
                select(
                    Worklog.issue_id,
                    Worklog.employee_id,
                    Worklog.hours,
                    Worklog.started_at,
                    Employee.display_name,
                    Employee.team,
                    Employee.role,
                )
                .join(Employee, Employee.id == Worklog.employee_id)
                .where(
                    Worklog.issue_id.in_(issue_ids),
                    Worklog.started_at >= datetime.combine(start_d, time.min),
                    Worklog.started_at <= end_dt,
                )
            )
            worklog_rows = list(self.db.execute(wl_q).all())

        # Aggregate per issue
        per_issue: dict[str, dict] = {}
        all_employees: set[str] = set()
        for issue in issues:
            per_issue[issue.id] = {
                "issue_id": issue.id,
                "key": issue.key,
                "summary": issue.summary,
                "hours": 0.0,
                "worklog_count": 0,
                "is_done": (issue.status or "").lower() == "done",
                "employees": defaultdict(
                    lambda: {"name": "", "role": "", "team": "", "hours": 0.0}
                ),
                "teams": set(),
                "first_log": None,
                "last_log": None,
            }

        for row in worklog_rows:
            issue_id, emp_id, hours, started_at, name, team, role = row
            if issue_id not in per_issue:
                continue
            entry = per_issue[issue_id]
            entry["hours"] += float(hours)
            entry["worklog_count"] += 1
            e = entry["employees"][emp_id]
            e["name"] = name
            e["role"] = role
            e["team"] = team
            e["hours"] += float(hours)
            if team:
                entry["teams"].add(team)
            all_employees.add(name)
            if entry["first_log"] is None or started_at < entry["first_log"]:
                entry["first_log"] = started_at
            if entry["last_log"] is None or started_at > entry["last_log"]:
                entry["last_log"] = started_at

        for entry in per_issue.values():
            if entry["first_log"] and entry["last_log"]:
                entry["days_in_progress"] = (
                    entry["last_log"] - entry["first_log"]
                ).days + 1
            else:
                entry["days_in_progress"] = 0
            entry["distinct_workers"] = len(entry["employees"])

        # Group by theme (or candidate_name for "Other")
        themes_by_id = {t.id: t for t in themes}
        per_theme: dict[str, dict] = {}
        candidates_agg: dict[str, dict] = {}
        manual_review: list[dict] = []

        for issue in issues:
            entry = per_issue.get(issue.id)
            if not entry or entry["hours"] == 0.0:
                continue
            cls = classifications.get(issue.id)
            if cls and cls.failed:
                manual_review.append({
                    "issue_id": issue.id,
                    "key": issue.key,
                    "summary": issue.summary,
                    "hours": round(entry["hours"], 2),
                    "failure_reason": cls.failure_reason,
                })
                continue

            if cls and cls.theme_id and cls.theme_id in themes_by_id:
                key = cls.theme_id
                if key not in per_theme:
                    th = themes_by_id[cls.theme_id]
                    per_theme[key] = {
                        "theme_id": th.id,
                        "name": th.name,
                        "color": th.color,
                        "is_archived": th.is_archived,
                        "issues": [],
                    }
                per_theme[key]["issues"].append({"entry": entry, "cls": cls})
            else:
                cand_name = (cls.candidate_name if cls else None) or "Другое"
                if cand_name not in candidates_agg:
                    candidates_agg[cand_name] = {
                        "proposed_name": cand_name,
                        "issues": [],
                        "hours": 0.0,
                    }
                candidates_agg[cand_name]["issues"].append({"entry": entry, "cls": cls})
                candidates_agg[cand_name]["hours"] += entry["hours"]

        total_hours = sum(e["hours"] for e in per_issue.values())
        total_tasks = sum(1 for e in per_issue.values() if e["hours"] > 0)
        total_employees = len(all_employees)

        # Build themes payload
        themes_out: list[dict] = []
        outliers: list[dict] = []

        for theme_key, t in per_theme.items():
            t_hours = sum(x["entry"]["hours"] for x in t["issues"])
            t_tasks_count = len(t["issues"])
            t_employees: dict[str, dict] = {}
            for x in t["issues"]:
                for emp_id, info in x["entry"]["employees"].items():
                    e = t_employees.setdefault(
                        emp_id,
                        {
                            "employee_id": emp_id,
                            "name": info["name"],
                            "role": info["role"],
                            "team": info["team"],
                            "hours": 0.0,
                        },
                    )
                    e["hours"] += info["hours"]

            top_tasks = sorted(t["issues"], key=lambda x: -x["entry"]["hours"])[:5]
            top_tasks_payload = [
                {
                    "key": x["entry"]["key"],
                    "summary": x["entry"]["summary"],
                    "hours": round(x["entry"]["hours"], 2),
                    "contribution": (x["cls"].contribution_text if x["cls"] else None),
                }
                for x in top_tasks
            ]
            issues_payload = [
                {
                    "issue_id": x["entry"]["issue_id"],
                    "key": x["entry"]["key"],
                    "summary": x["entry"]["summary"],
                    "hours": round(x["entry"]["hours"], 2),
                    "contribution": (x["cls"].contribution_text if x["cls"] else None),
                    "employee_breakdown": [
                        {
                            "name": info["name"],
                            "role": info["role"],
                            "team": info["team"],
                            "hours": round(info["hours"], 2),
                        }
                        for info in x["entry"]["employees"].values()
                    ],
                }
                for x in t["issues"]
            ]
            evidence_keys = [tt["key"] for tt in top_tasks_payload]

            theme_payload = {
                "theme_id": t["theme_id"],
                "name": t["name"],
                "color": t["color"],
                "is_new": False,
                "totals": {
                    "hours": round(t_hours, 2),
                    "pct": round(100 * t_hours / total_hours, 1) if total_hours else 0,
                    "tasks_count": t_tasks_count,
                    "employees_count": len(t_employees),
                },
                "by_employee": [
                    {
                        "employee_id": k,
                        "hours": round(v["hours"], 2),
                        "name": v["name"],
                        "role": v["role"],
                        "team": v["team"],
                    }
                    for k, v in t_employees.items()
                ],
                "top_tasks": top_tasks_payload,
                "issues": issues_payload,
                "evidence_keys": evidence_keys,
            }
            themes_out.append(theme_payload)

            # Outliers per theme
            theme_issues_for_outlier = [
                {
                    "issue_id": x["entry"]["issue_id"],
                    "key": x["entry"]["key"],
                    "summary": x["entry"]["summary"],
                    "hours": round(x["entry"]["hours"], 2),
                    "distinct_workers": x["entry"]["distinct_workers"],
                    "days_in_progress": x["entry"]["days_in_progress"],
                    "reopen_count": 0,
                    "worklog_count": x["entry"]["worklog_count"],
                    "is_done": x["entry"]["is_done"],
                }
                for x in t["issues"]
            ]
            for o in detect_outliers_for_theme({}, theme_issues=theme_issues_for_outlier):
                outliers.append({
                    "key": o.issue_key,
                    "issue_id": o.issue_id,
                    "reason": o.reason,
                    "value": o.value,
                    "context": o.context,
                })

        themes_out.sort(key=lambda t: -t["totals"]["hours"])

        # Candidates
        candidates_payload: list[dict] = []
        for name, agg in candidates_agg.items():
            sample_keys = [x["entry"]["key"] for x in agg["issues"][:5]]
            candidates_payload.append({
                "proposed_name": name,
                "issues_count": len(agg["issues"]),
                "hours": round(agg["hours"], 2),
                "sample_keys": sample_keys,
            })
        candidates_payload.sort(key=lambda c: -c["hours"])

        findings = {
            "totals": {
                "hours": round(total_hours, 2),
                "tasks": total_tasks,
                "employees": total_employees,
                "themes_count": len(themes_out),
            },
            "themes": themes_out,
            "candidates": candidates_payload,
            "outliers": outliers,
        }
        return findings, manual_review, all_employees

    def _build_snapshot_data(
        self,
        findings: dict,
        synthesis: SynthesisOutput,
        manual_review: list[dict],
    ) -> dict:
        # Inject theme narratives into themes
        theme_narratives_by_id = {
            n.get("theme_id"): n.get("narrative", "")
            for n in synthesis.themes_narratives
        }
        outlier_explanations_by_key = {
            n.get("key"): n.get("explanation", "")
            for n in synthesis.outliers_explanations
        }

        themes_with_text = []
        for t in findings["themes"]:
            t = dict(t)
            t["narrative"] = theme_narratives_by_id.get(t["theme_id"], "")
            themes_with_text.append(t)

        outliers_with_text = []
        for o in findings.get("outliers", []):
            o = dict(o)
            o["explanation"] = outlier_explanations_by_key.get(o.get("key"), "")
            outliers_with_text.append(o)

        return {
            "headline": synthesis.headline,
            "totals": findings["totals"],
            "themes": themes_with_text,
            "candidates": findings.get("candidates", []),
            "outliers": outliers_with_text,
            "recommendation": synthesis.recommendation,
            "manual_review_required": manual_review,
            "is_fallback_narrative": synthesis.is_fallback,
        }
