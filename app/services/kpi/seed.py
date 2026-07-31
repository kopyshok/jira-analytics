"""Шесть метрик KPI и профиль «Аналитик» по умолчанию.

Наборы условий заведены дословно по разделу 3 спеки
(docs/superpowers/specs/2026-07-30-kpi-analysts-design.md). Продуктовое
направление — фильтр отчёта (параметр ``direction`` у ``GET /kpi/report``,
Фаза 4), поэтому в условиях метрик не зашито конкретное значение.
"""
import json

from sqlalchemy.orm import Session

from app.models.kpi import KpiMetric, KpiProfile, KpiProfileMetric

PROJECT_1C = "OS"  # «1С» из ТЗ — проект с ключом OS (см. раздел 4 спеки)
EPIC_OR_IT_TASK = ["Эпик", "ИТ-задача"]
# «Соблюдение сроков» — только эпики (квартальная цель = эпик, уточнение
# заказчика поверх ТЗ, см. раздел 3.2 спеки).
EPIC_ONLY = ["Эпик"]
PROJECT_SUBTYPES = ["RFC_STANDARD", "PROJECT"]
# «Готово» из ТЗ — значение резолюции этого арендатора Jira называется Done
# (см. раздел 3.8 спеки).
RESOLUTION_DONE = "Done"


def _ensure_metric(db: Session, metric: KpiMetric) -> KpiMetric:
    """Создать метрику, если код ещё не занят; иначе вернуть существующую."""
    existing = db.query(KpiMetric).filter_by(code=metric.code).first()
    if existing is not None:
        return existing
    db.add(metric)
    db.flush()
    return metric


def _ensure_profile(db: Session, profile: KpiProfile) -> KpiProfile:
    """Создать профиль, если код ещё не занят; иначе вернуть существующий."""
    existing = db.query(KpiProfile).filter_by(code=profile.code).first()
    if existing is not None:
        return existing
    db.add(profile)
    db.flush()
    return profile


def _ensure_profile_metric(db: Session, profile: KpiProfile, metric: KpiMetric,
                           weight: float, sort_order: int) -> None:
    """Привязать метрику к профилю с весом, если связи ещё нет."""
    existing = (
        db.query(KpiProfileMetric)
        .filter_by(profile_id=profile.id, metric_id=metric.id)
        .first()
    )
    if existing is not None:
        return
    db.add(KpiProfileMetric(
        profile_id=profile.id, metric_id=metric.id, weight=weight, sort_order=sort_order,
    ))


def seed_defaults(db: Session) -> None:
    """Завести шесть метрик и профиль «Аналитик», если их ещё нет.

    Идемпотентно: повторный вызов не создаёт дублей метрик и не дублирует
    веса в профиле (миграция, вызывающая эту функцию, может быть применена
    к уже заполненной базе при пересборе dev-окружения).
    """
    quality = _ensure_metric(db, KpiMetric(
        code="quality",
        name="Качество выпуска",
        description="100 − доля багов на проде от выпущенных задач автора, при нуле багов — 100",
        calc_kind="ratio", invert=True, cap_at_100=True, is_builtin=True, sort_order=10,
        numerator_json=json.dumps({
            "unit": "issues", "person_field": "linked_issue_author",
            "period_window": "closed_in",
            "conditions": [
                {"attr": "project_key", "op": "in", "value": [PROJECT_1C]},
                {"attr": "issue_type", "op": "in", "value": ["Баг"]},
                {"attr": "resolution", "op": "in", "value": [RESOLUTION_DONE]},
                {"attr": "environment", "op": "eq", "value": "PROD"},
            ],
        }, ensure_ascii=False),
        denominator_json=json.dumps({
            "unit": "issues", "person_field": "author",
            "period_window": "closed_in",
            "conditions": [
                {"attr": "project_key", "op": "in", "value": [PROJECT_1C]},
                {"attr": "issue_type", "op": "in", "value": ["Задача", "Баг"]},
                {"attr": "resolution", "op": "in", "value": [RESOLUTION_DONE]},
            ],
        }, ensure_ascii=False),
    ))

    deadlines = _ensure_metric(db, KpiMetric(
        code="deadlines",
        name="Соблюдение сроков",
        description="Доля задач исполнителя, выполненных не позже плановой даты окончания",
        calc_kind="ratio", invert=False, cap_at_100=True, is_builtin=True, sort_order=20,
        numerator_json=json.dumps({
            "unit": "issues", "person_field": "assignee",
            "period_window": "closed_in",
            "conditions": [
                {"attr": "issue_type", "op": "in", "value": EPIC_ONLY},
                {"attr": "subtype", "op": "in", "value": PROJECT_SUBTYPES},
                {"attr": "resolution", "op": "in", "value": [RESOLUTION_DONE]},
                {"attr": "resolved_on_time", "op": "is_true", "value": None},
            ],
        }, ensure_ascii=False),
        denominator_json=json.dumps({
            "unit": "issues", "person_field": "assignee",
            "period_window": "closed_in",
            "conditions": [
                {"attr": "issue_type", "op": "in", "value": EPIC_ONLY},
                {"attr": "subtype", "op": "in", "value": PROJECT_SUBTYPES},
                {"attr": "resolution", "op": "in", "value": [RESOLUTION_DONE]},
            ],
        }, ensure_ascii=False),
    ))

    regulations = _ensure_metric(db, KpiMetric(
        code="regulations",
        name="Соблюдение регламентов",
        description="Доля задач, поставленных в разработку с заполненными обязательными полями",
        calc_kind="ratio", invert=False, cap_at_100=True, is_builtin=True, sort_order=30,
        numerator_json=json.dumps({
            "unit": "issues", "person_field": "author",
            "period_window": "created_and_closed_in",
            "conditions": [
                {"attr": "project_key", "op": "in", "value": [PROJECT_1C]},
                {"attr": "issue_type", "op": "in", "value": ["Задача"]},
                {"attr": "status", "op": "not_in", "value": ["Backlog", "Бэклог"]},
                {"attr": "field_filled", "op": "all",
                 "value": ["goal_text", "current_behavior", "description"]},
            ],
        }, ensure_ascii=False),
        denominator_json=json.dumps({
            "unit": "issues", "person_field": "author",
            "period_window": "created_and_closed_in",
            "conditions": [
                {"attr": "project_key", "op": "in", "value": [PROJECT_1C]},
                {"attr": "issue_type", "op": "in", "value": ["Задача"]},
                {"attr": "status", "op": "not_in", "value": ["Backlog", "Бэклог"]},
            ],
        }, ensure_ascii=False),
    ))

    cycle_time = _ensure_metric(db, KpiMetric(
        code="cycle_time",
        name="Cycle Time",
        description="Норматив команды на квартал делённый на средний фактический цикл, потолок 100",
        calc_kind="norm_to_fact", invert=False, cap_at_100=True, is_builtin=True, sort_order=40,
        fact_field="cycle_time_fact",
        numerator_json=json.dumps({
            "unit": "issues", "person_field": "assignee",
            "period_window": "closed_in",
            "conditions": [
                {"attr": "issue_type", "op": "in", "value": EPIC_OR_IT_TASK},
                {"attr": "subtype", "op": "in", "value": PROJECT_SUBTYPES},
                {"attr": "resolution", "op": "in", "value": [RESOLUTION_DONE]},
                {"attr": "cost_type", "op": "eq", "value": "Change"},
            ],
        }, ensure_ascii=False),
    ))

    customer_score = _ensure_metric(db, KpiMetric(
        code="customer_score",
        name="Оценка заказчика",
        description="Средний балл заказчика (скорость, качество, результат) от максимума 5",
        calc_kind="score_to_max", invert=False, cap_at_100=True, is_builtin=True, sort_order=50,
        score_fields=json.dumps(["rating_speed", "rating_quality", "rating_result"]),
        score_max=5.0,
        numerator_json=json.dumps({
            "unit": "issues", "person_field": "assignee",
            "period_window": "created_and_closed_in",
            "conditions": [
                {"attr": "issue_type", "op": "in", "value": EPIC_OR_IT_TASK},
                {"attr": "subtype", "op": "in", "value": PROJECT_SUBTYPES},
                {"attr": "resolution", "op": "in", "value": [RESOLUTION_DONE]},
            ],
        }, ensure_ascii=False),
    ))

    worklog_timeliness = _ensure_metric(db, KpiMetric(
        code="worklog_timeliness",
        name="Своевременность трудозатрат",
        description="Доля записей о трудозатратах, внесённых не позже срока по производственному календарю",
        calc_kind="ratio", invert=True, cap_at_100=True, is_builtin=True, sort_order=60,
        numerator_json=json.dumps({
            "unit": "worklogs", "person_field": "worklog_author",
            "period_window": "closed_in",
            "conditions": [
                {"attr": "project_key", "op": "in", "value": ["OS", "PMD", "AD"]},
            ],
        }, ensure_ascii=False),
        denominator_json=None,
    ))

    profile = _ensure_profile(db, KpiProfile(
        code="analyst", name="Аналитик", role_code="analyst",
        target_pct=80.0, warn_band_pct=10.0, is_enabled=True,
        # Спека допускает оценку руководителей проектов профилем «Аналитик»,
        # пока для них не заведён свой — явный запасной профиль по
        # умолчанию, а не первый попавшийся по случайному порядку выборки.
        is_default=True,
    ))

    weighted_metrics = [
        (quality, 0.2, 10), (deadlines, 0.2, 20), (regulations, 0.2, 30),
        (cycle_time, 0.2, 40), (customer_score, 0.1, 50), (worklog_timeliness, 0.1, 60),
    ]
    for metric, weight, sort_order in weighted_metrics:
        _ensure_profile_metric(db, profile, metric, weight, sort_order)
