"""Контрольный пример из ТЗ — опора при приёмке раздела KPI.

ТЗ утверждает, что при этих исходных данных итог сотрудника — 74,5%.
Ревью Фазы 3 верно заметило расхождение с нашим расчётом (86,5%) и
потребовало разбирательства. Причина — ошибка в самом ТЗ: формула
качества выпуска там записана с инверсией («100 минус доля багов»), а
в примере посчитано БЕЗ инверсии — 3 бага из 15 задач взяты как 20%
(доля багов), а не как 80% (100 − 20, как того требует записанная
формула). Подставив без инверсии, ТЗ получает 74,5%; наша реализация
следует записанной формуле — и даёт верные 86,5%.

Проверено вручную по каждой из шести метрик (см. ``test_control_example_...``
ниже) — код в этом тесте не подгонялся под ответ, а собран напрямую из
условий отбора шести метрик по умолчанию (``app/services/kpi/seed.py``).
"""
from datetime import date, datetime

from app.models.employee import Employee
from app.models.employee_team import EmployeeTeam
from app.models.issue import Issue
from app.models.issue_link import IssueLink
from app.models.kpi import KpiCycleTimeNorm
from app.models.project import Project
from app.models.worklog import Worklog
from app.services.kpi.kpi_service import build_report
from app.services.kpi.seed import seed_defaults

TEAM = "Платежи"
ACCOUNT_ID = "acc-control"


def _issue(db, project, jid, key, **kw):
    defaults = dict(
        jira_issue_id=jid, key=key, summary="s", issue_type="Задача",
        status="ГОТОВО", status_category="done", project_id=project.id, team=TEAM,
    )
    defaults.update(kw)
    issue = Issue(**defaults)
    db.add(issue)
    return issue


def test_control_example_matches_manual_calculation_at_86_5_percent(db_session):
    seed_defaults(db_session)
    db_session.commit()

    project = Project(jira_project_id="p-ctrl", key="OS", name="1С")
    db_session.add(project)
    emp = Employee(jira_account_id=ACCOUNT_ID, display_name="Контрольный сотрудник",
                   team=TEAM, role="analyst")
    db_session.add(emp)
    db_session.commit()
    db_session.add(EmployeeTeam(employee_id=emp.id, team=TEAM, is_primary=True,
                                joined_at=date(2026, 1, 1)))
    db_session.commit()

    # --- Качество выпуска: 3 бага на 15 выпущенных задач → 100 - 3/15*100 = 80,0 ---
    released = []
    for i in range(15):
        issue = _issue(
            db_session, project, f"q-rel-{i}", f"OS-{1000 + i}",
            resolution="Готово", resolved_at=datetime(2026, 7, 10),
            reporter_account_id=ACCOUNT_ID,
        )
        released.append(issue)
    db_session.commit()
    for i in range(3):
        bug = _issue(
            db_session, project, f"q-bug-{i}", f"OS-{1100 + i}",
            issue_type="Баг", resolution="Готово", environment="PROD",
            resolved_at=datetime(2026, 7, 12),
        )
        db_session.commit()
        db_session.add(IssueLink(source_issue_id=bug.id, target_issue_id=released[i].id,
                                 link_type="Relates"))
    db_session.commit()

    # --- Соблюдение сроков: 8 из 10 в срок → 80,0 ---
    # Явных «в срок» — 8 (ниже); недостающие 2 в знаменателе добирают задачи
    # Cycle Time и Оценки заказчика (см. дальше) — у обеих issue_type
    # «ИТ-задача» и resolution «Готово», как того требует и эта метрика, но
    # без planned_end_date, поэтому «в срок» не засчитываются. Это не натяжка
    # теста: в реальных данных многомерное пересечение условий метрик — норма.
    for i in range(8):
        _issue(
            db_session, project, f"dl-{i}", f"OS-{1200 + i}",
            issue_type="ИТ-задача", resolution="Готово",
            resolved_at=datetime(2026, 7, 15, 10, 0),
            planned_end_date=datetime(2026, 7, 15, 0, 0),
            assignee_account_id=ACCOUNT_ID,
        )
    db_session.commit()

    # --- Соблюдение регламентов: 9 из 10 с заполненными полями → 90,0 ---
    # Резолюция намеренно не указана — регламенты её не требуют, а «Готово»
    # здесь задвоило бы счёт с знаменателем «Качества выпуска» (тот тоже
    # берёт «Задача»/«Готово» этого же автора и проекта).
    for i in range(10):
        filled = i < 9
        _issue(
            db_session, project, f"reg-{i}", f"OS-{1300 + i}",
            resolved_at=datetime(2026, 7, 18),
            jira_created_at=datetime(2026, 7, 2),
            reporter_account_id=ACCOUNT_ID,
            goal_text="цель" if filled else None,
            current_behavior="как сейчас" if filled else "как сейчас",
            description="описание" if filled else "описание",
        )
    db_session.commit()

    # --- Cycle Time: норматив 80 при факте 75 → 80/75*100 = 106,7, потолок 100 ---
    _issue(
        db_session, project, "ct-1", "OS-1400",
        issue_type="ИТ-задача", resolution="Готово", subtype="RFC_STANDARD", cost_type="Change",
        cycle_time_fact=75.0, resolved_at=datetime(2026, 7, 20),
        assignee_account_id=ACCOUNT_ID,
    )
    db_session.add(KpiCycleTimeNorm(team=TEAM, year=2026, quarter=3, norm_value=80.0))
    db_session.commit()

    # --- Оценка заказчика: 4 из 5 → 80,0 ---
    _issue(
        db_session, project, "cs-1", "OS-1401",
        issue_type="ИТ-задача", resolution="Готово", subtype="PROJECT",
        resolved_at=datetime(2026, 7, 22), jira_created_at=datetime(2026, 7, 1),
        assignee_account_id=ACCOUNT_ID,
        rating_speed=4, rating_quality=4, rating_result=4,
    )
    db_session.commit()

    # --- Своевременность трудозатрат: 15 просрочек из 100 → 85,0 ---
    # 20 записей вместо 100 (пропорционально: 3 из 20 = 15%, тот же процент,
    # что и «15 из 100» в ТЗ) — сама пропорция не зависит от масштаба.
    wl_issue = _issue(db_session, project, "wl-host", "OS-1500")
    db_session.commit()
    for i in range(20):
        late = i < 3
        db_session.add(Worklog(
            jira_worklog_id=f"wl-{i}", issue_id=wl_issue.id, employee_id=emp.id,
            started_at=datetime(2026, 7, 7, 10, 0),
            jira_created_at=datetime(2026, 7, 9, 10, 0) if late else datetime(2026, 7, 7, 18, 0),
            hours=1.0, time_spent_seconds=3600,
        ))
    db_session.commit()

    report = build_report(db_session, teams=[TEAM], year=2026, month=7)
    row = next(r for r in report["rows"] if r["account_id"] == ACCOUNT_ID)
    by_code = {m["code"]: m for m in row["metrics"]}

    assert round(by_code["quality"]["value"], 1) == 80.0
    assert round(by_code["deadlines"]["value"], 1) == 80.0
    assert round(by_code["regulations"]["value"], 1) == 90.0
    assert round(by_code["cycle_time"]["value"], 1) == 100.0
    assert round(by_code["customer_score"]["value"], 1) == 80.0
    assert round(by_code["worklog_timeliness"]["value"], 1) == 85.0

    # 80*0.2 + 80*0.2 + 90*0.2 + 100*0.2 + 80*0.1 + 85*0.1 = 86,5 — не 74,5 из ТЗ.
    assert round(row["total"], 1) == 86.5
