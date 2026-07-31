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
import json
from datetime import date, datetime

from app.models.app_setting import AppSetting
from app.models.employee import Employee
from app.models.employee_team import EmployeeTeam
from app.models.issue import Issue
from app.models.issue_link import IssueLink
from app.models.kpi import KpiCycleTimeNorm, KpiMetric, KpiProfile, KpiProfileMetric
from app.models.project import Project
from app.models.worklog import Worklog
from app.services.kpi.kpi_service import (
    build_approval_payload,
    build_report,
    report_with_approvals,
    save_approval,
)
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
            resolution="Done", resolved_at=datetime(2026, 7, 10),
            reporter_account_id=ACCOUNT_ID,
        )
        released.append(issue)
    db_session.commit()
    for i in range(3):
        bug = _issue(
            db_session, project, f"q-bug-{i}", f"OS-{1100 + i}",
            issue_type="Баг", resolution="Done", environment="PROD",
            resolved_at=datetime(2026, 7, 12),
        )
        db_session.commit()
        db_session.add(IssueLink(source_issue_id=bug.id, target_issue_id=released[i].id,
                                 link_type="Relates"))
    db_session.commit()

    # --- Соблюдение сроков: 8 из 10 в срок → 80,0 ---
    # Метрика оценивает квартальную цель — эпик (уточнение заказчика, раздел
    # 3.2 спеки); ИТ-задача сюда больше не попадает, поэтому все 10 задач
    # знаменателя заведены явно типом «Эпик», а не добираются пересечением с
    # Cycle Time/Оценкой заказчика (у тех — «ИТ-задача», в этот знаменатель
    # больше не входит).
    for i in range(8):
        _issue(
            db_session, project, f"dl-{i}", f"OS-{1200 + i}",
            issue_type="Эпик", resolution="Done",
            resolved_at=datetime(2026, 7, 15, 10, 0),
            planned_end_date=datetime(2026, 7, 15, 0, 0),
            assignee_account_id=ACCOUNT_ID,
        )
    for i in range(2):
        _issue(
            db_session, project, f"dl-late-{i}", f"OS-{1250 + i}",
            issue_type="Эпик", resolution="Done",
            resolved_at=datetime(2026, 7, 16, 10, 0),
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
        issue_type="ИТ-задача", resolution="Done", subtype="RFC_STANDARD", cost_type="Change",
        cycle_time_fact=75.0, resolved_at=datetime(2026, 7, 20),
        assignee_account_id=ACCOUNT_ID,
    )
    db_session.add(KpiCycleTimeNorm(team=TEAM, year=2026, quarter=3, norm_value=80.0))
    db_session.commit()

    # --- Оценка заказчика: 4 из 5 → 80,0 ---
    _issue(
        db_session, project, "cs-1", "OS-1401",
        issue_type="ИТ-задача", resolution="Done", subtype="PROJECT",
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


def test_new_metric_added_as_dictionary_row_is_computed_without_code_changes(db_session):
    """Пункт 1 раздела 10: шесть метрик собираются из справочника без правки кода.

    Сами шесть встроенных метрик и сумма их весов уже проверены в
    ``tests/services/test_kpi_seed.py``. Здесь проверяется сам принцип
    (спека, раздел 2: «Седьмая метрика того же вида заводится без
    разработки») — заводим седьмую метрику как обычную запись в справочнике,
    как это сделал бы руководитель через настройки, и убеждаемся, что
    расчёт отчёта подхватывает её наравне со штатными шестью: движок не
    содержит ветвлений по коду конкретной метрики, только по способу расчёта.
    """
    seed_defaults(db_session)
    db_session.commit()

    project = Project(jira_project_id="p-new-metric", key="OS", name="1С")
    db_session.add(project)
    emp = Employee(jira_account_id="acc-new-metric", display_name="Новикова Н.",
                   team=TEAM, role="analyst")
    db_session.add(emp)
    db_session.commit()
    db_session.add(EmployeeTeam(employee_id=emp.id, team=TEAM, is_primary=True,
                                joined_at=date(2026, 1, 1)))

    for i in range(4):
        db_session.add(Issue(
            jira_issue_id=f"nm-{i}", key=f"OS-{2000 + i}", summary="s", issue_type="Задача",
            status="ГОТОВО", status_category="done", resolution="Done",
            resolved_at=datetime(2026, 7, 10), project_id=project.id,
            reporter_account_id="acc-new-metric", team=TEAM,
        ))
    db_session.commit()

    # Метрика заведена как чистые данные: те же условия числителя и
    # знаменателя (все задачи автора без исключений) дают 100% при условии,
    # что движок реально прочитал JSON новой метрики, а не пропустил её.
    cond = json.dumps({
        "unit": "issues", "person_field": "author", "period_window": "closed_in",
        "conditions": [{"attr": "issue_type", "op": "in", "value": ["Задача"]}],
    })
    new_metric = KpiMetric(
        code="new_metric_from_dictionary", name="Новая метрика руководителя",
        calc_kind="ratio", invert=False, cap_at_100=True, is_builtin=False,
        numerator_json=cond, denominator_json=cond,
    )
    db_session.add(new_metric)
    db_session.commit()

    profile = db_session.query(KpiProfile).filter_by(code="analyst").one()
    db_session.add(KpiProfileMetric(profile_id=profile.id, metric_id=new_metric.id, weight=0.1))
    db_session.commit()

    report = build_report(db_session, teams=[TEAM], year=2026, month=7)
    row = next(r for r in report["rows"] if r["account_id"] == "acc-new-metric")
    new_metric_result = next(
        m for m in row["metrics"] if m["code"] == "new_metric_from_dictionary"
    )
    assert new_metric_result["has_data"] is True
    assert round(new_metric_result["value"], 1) == 100.0


def test_cancelled_issue_excluded_from_denominator(db_session):
    """Пункт 3 раздела 10: отменённые задачи не попадают в знаменатели.

    Трансляция условий отбора уже проверена по кускам в
    ``tests/services/test_kpi_conditions.py::TestExcludedStatusesTrimDenominator``.
    Здесь — приёмочная проверка целиком: реальный отчёт по сотруднику с
    задачей в статусе «Отменено» (спека, раздел 6) не должен считать её ни
    в числителе, ни в знаменателе метрики «Качество выпуска», даже если у
    неё формально заполнена резолюция «Готово» — именно статус, а не
    резолюция, определяет исключение.
    """
    seed_defaults(db_session)
    db_session.commit()

    project = Project(jira_project_id="p-cancel", key="OS", name="1С")
    db_session.add(project)
    emp = Employee(jira_account_id="acc-cancel", display_name="Отменённый О.",
                   team=TEAM, role="analyst")
    db_session.add(emp)
    db_session.commit()
    db_session.add(EmployeeTeam(employee_id=emp.id, team=TEAM, is_primary=True,
                                joined_at=date(2026, 1, 1)))

    db_session.add(Issue(
        jira_issue_id="cx-1", key="OS-3000", summary="s", issue_type="Задача",
        status="Отменено", status_category="done", resolution="Done",
        resolved_at=datetime(2026, 7, 10), project_id=project.id,
        reporter_account_id="acc-cancel", team=TEAM,
    ))
    db_session.add(Issue(
        jira_issue_id="cx-2", key="OS-3001", summary="s", issue_type="Задача",
        status="ГОТОВО", status_category="done", resolution="Done",
        resolved_at=datetime(2026, 7, 12), project_id=project.id,
        reporter_account_id="acc-cancel", team=TEAM,
    ))
    db_session.commit()

    report = build_report(db_session, teams=[TEAM], year=2026, month=7)
    row = next(r for r in report["rows"] if r["account_id"] == "acc-cancel")
    quality = next(m for m in row["metrics"] if m["code"] == "quality")

    assert quality["denominator"] == 1
    assert quality["numerator"] == 0
    assert round(quality["value"], 1) == 100.0


def test_employee_moved_between_teams_mid_month_not_duplicated(db_session):
    """Пункт 4 раздела 10: сотрудник, перешедший между командами в середине
    месяца, не задваивается.

    Одновременное состояние в двух командах и норматив по исторической
    команде по отдельности уже проверены в
    ``tests/services/test_kpi_report.py``
    (``test_employee_in_two_teams_not_duplicated``,
    ``test_cycle_time_norm_uses_team_at_period_start_not_current_team``).
    Здесь — сценарий именно из пункта приёмки: сотрудник СОСТОЯЛ в одной
    команде и ПЕРЕШЁЛ в другую 16 июля, руководитель смотрит отчёт сразу по
    обеим командам — ожидаем одну строку на сотрудника, и обе задачи (одна
    до переезда, одна после) засчитаны по одному разу каждая, а не потеряны
    и не задвоены.
    """
    team_before = "Отдел разработки"
    team_after = "Отдел аналитики"
    account_id = "acc-mover"

    project = Project(jira_project_id="p-mover", key="OS", name="1С")
    db_session.add(project)
    emp = Employee(jira_account_id=account_id, display_name="Сидоров С.",
                   team=team_after, role="analyst")
    db_session.add(emp)
    db_session.commit()
    db_session.add(EmployeeTeam(employee_id=emp.id, team=team_before, is_primary=True,
                                joined_at=date(2026, 1, 1), left_at=date(2026, 7, 16)))
    db_session.add(EmployeeTeam(employee_id=emp.id, team=team_after, is_primary=True,
                                joined_at=date(2026, 7, 16)))

    seed_defaults(db_session)
    db_session.commit()

    db_session.add(Issue(
        jira_issue_id="mv-1", key="OS-4000", summary="до переезда", issue_type="Задача",
        status="ГОТОВО", status_category="done", resolution="Done",
        resolved_at=datetime(2026, 7, 5), project_id=project.id,
        reporter_account_id=account_id, team=team_before,
    ))
    db_session.add(Issue(
        jira_issue_id="mv-2", key="OS-4001", summary="после переезда", issue_type="Задача",
        status="ГОТОВО", status_category="done", resolution="Done",
        resolved_at=datetime(2026, 7, 25), project_id=project.id,
        reporter_account_id=account_id, team=team_after,
    ))
    db_session.commit()

    report = build_report(db_session, teams=[team_before, team_after], year=2026, month=7)
    matching_rows = [r for r in report["rows"] if r["account_id"] == account_id]
    assert len(matching_rows) == 1

    quality = next(m for m in matching_rows[0]["metrics"] if m["code"] == "quality")
    assert quality["denominator"] == 2


def test_metric_without_data_redistributes_weight_not_zeroes_total(db_session):
    """Пункт 5 раздела 10: метрика без данных не обнуляет итог, а
    перераспределяет вес.

    Арифметика самого перераспределения (функция ``combine``) уже проверена
    в ``tests/services/test_kpi_service.py``. Здесь — приёмочная проверка на
    реальном отчёте по всем шести штатным метрикам: у сотрудника есть данные
    по пяти метрикам, но нет ни одной задачи с оценкой заказчика. Итог
    обязан остаться взвешенным средним по пяти метрикам с весами,
    перенормированными к единице (87,2%), а не быть посчитан так, будто
    отсутствующая метрика равна нулю (дало бы 78,5%) или сотня (89,5%).
    """
    seed_defaults(db_session)
    db_session.commit()

    project = Project(jira_project_id="p-nodata", key="OS", name="1С")
    db_session.add(project)
    account_id = "acc-nodata"
    emp = Employee(jira_account_id=account_id, display_name="Безданных Б.",
                   team=TEAM, role="analyst")
    db_session.add(emp)
    db_session.commit()
    db_session.add(EmployeeTeam(employee_id=emp.id, team=TEAM, is_primary=True,
                                joined_at=date(2026, 1, 1)))

    # Качество выпуска: 3 бага на 15 выпущенных задач → 80,0
    released = []
    for i in range(15):
        issue = Issue(
            jira_issue_id=f"nd-rel-{i}", key=f"OS-{5000 + i}", summary="s", issue_type="Задача",
            status="ГОТОВО", status_category="done", resolution="Done",
            resolved_at=datetime(2026, 7, 10), project_id=project.id,
            reporter_account_id=account_id, team=TEAM,
        )
        db_session.add(issue)
        released.append(issue)
    db_session.commit()
    for i in range(3):
        bug = Issue(
            jira_issue_id=f"nd-bug-{i}", key=f"OS-{5100 + i}", summary="s", issue_type="Баг",
            status="ГОТОВО", status_category="done", resolution="Done", environment="PROD",
            resolved_at=datetime(2026, 7, 12), project_id=project.id, team=TEAM,
        )
        db_session.add(bug)
        db_session.commit()
        db_session.add(IssueLink(source_issue_id=bug.id, target_issue_id=released[i].id,
                                 link_type="Relates"))
    db_session.commit()

    # Соблюдение сроков: 8 в срок из 9. Метрика оценивает квартальную
    # цель — эпик (раздел 3.2 спеки), поэтому знаменатель заведён явно
    # девятью задачами типа «Эпик», а не добирается пересечением с Cycle
    # Time (у той — «ИТ-задача», в этот знаменатель больше не входит).
    for i in range(8):
        db_session.add(Issue(
            jira_issue_id=f"nd-dl-{i}", key=f"OS-{5200 + i}", summary="s",
            issue_type="Эпик", status="ГОТОВО", status_category="done",
            resolution="Done", resolved_at=datetime(2026, 7, 15, 10, 0),
            planned_end_date=datetime(2026, 7, 15, 0, 0), project_id=project.id,
            assignee_account_id=account_id, team=TEAM,
        ))
    db_session.add(Issue(
        jira_issue_id="nd-dl-late", key="OS-5250", summary="s",
        issue_type="Эпик", status="ГОТОВО", status_category="done",
        resolution="Done", resolved_at=datetime(2026, 7, 16, 10, 0),
        planned_end_date=datetime(2026, 7, 15, 0, 0), project_id=project.id,
        assignee_account_id=account_id, team=TEAM,
    ))
    db_session.commit()

    # Соблюдение регламентов: 9 из 10 с заполненными полями → 90,0
    for i in range(10):
        filled = i < 9
        db_session.add(Issue(
            jira_issue_id=f"nd-reg-{i}", key=f"OS-{5300 + i}", summary="s", issue_type="Задача",
            status="ГОТОВО", status_category="done", resolved_at=datetime(2026, 7, 18),
            jira_created_at=datetime(2026, 7, 2), project_id=project.id,
            reporter_account_id=account_id, team=TEAM,
            goal_text="цель" if filled else None,
            current_behavior="как сейчас", description="описание",
        ))
    db_session.commit()

    # Cycle Time: норматив 80 при факте 75 → 106,7, потолок 100
    db_session.add(Issue(
        jira_issue_id="nd-ct-1", key="OS-5400", summary="s", issue_type="ИТ-задача",
        status="ГОТОВО", status_category="done", resolution="Done",
        subtype="RFC_STANDARD", cost_type="Change", cycle_time_fact=75.0,
        resolved_at=datetime(2026, 7, 20), project_id=project.id,
        assignee_account_id=account_id, team=TEAM,
    ))
    db_session.add(KpiCycleTimeNorm(team=TEAM, year=2026, quarter=3, norm_value=80.0))
    db_session.commit()

    # Своевременность трудозатрат: 3 просрочки из 20 → 85,0
    wl_issue = Issue(
        jira_issue_id="nd-wl-host", key="OS-5500", summary="s", issue_type="Задача",
        status="ГОТОВО", status_category="done", project_id=project.id, team=TEAM,
    )
    db_session.add(wl_issue)
    db_session.commit()
    for i in range(20):
        late = i < 3
        db_session.add(Worklog(
            jira_worklog_id=f"nd-wl-{i}", issue_id=wl_issue.id, employee_id=emp.id,
            started_at=datetime(2026, 7, 7, 10, 0),
            jira_created_at=datetime(2026, 7, 9, 10, 0) if late else datetime(2026, 7, 7, 18, 0),
            hours=1.0, time_spent_seconds=3600,
        ))
    db_session.commit()

    # Оценка заказчика: намеренно НИ ОДНОЙ подходящей задачи — метрика без данных.

    report = build_report(db_session, teams=[TEAM], year=2026, month=7)
    row = next(r for r in report["rows"] if r["account_id"] == account_id)
    by_code = {m["code"]: m for m in row["metrics"]}

    assert by_code["customer_score"]["has_data"] is False
    assert round(by_code["deadlines"]["value"], 2) == 88.89  # 8 из 9, см. комментарий выше
    # (80*0.2 + 88.89*0.2 + 90*0.2 + 100*0.2 + 85*0.1), делённое на сумму
    # оставшихся весов 0,9 (без веса 0,1 отсутствующей оценки заказчика) — не
    # на полную единицу (дало бы 80,3 — как будто отсутствующая метрика
    # равна нулю) и не сотню за неё (дало бы 90,3).
    assert round(row["total"], 1) == 89.2


def test_approved_month_frozen_after_weight_change(db_session):
    """Пункт 6 раздела 10: утверждённый месяц не меняется после правки весов.

    Утверждение через HTTP API (эндпоинт ``/kpi/approve``) и устойчивость к
    одновременному утверждению двумя руководителями уже проверены в
    ``tests/test_kpi_endpoints.py::TestApprovalFreeze`` и
    ``tests/services/test_kpi_approval.py``. Здесь та же гарантия
    проверяется на уровне сервиса расчёта, без TestClient: снимок обязан
    быть самодостаточным (веса профиля на момент утверждения уже разложены
    внутри него), а не пересчитываться по текущим весам при каждом чтении.
    """
    team = "Аналитика продаж"
    account_id = "acc-frozen"

    seed_defaults(db_session)
    db_session.commit()

    project = Project(jira_project_id="p-frozen", key="OS", name="1С")
    db_session.add(project)
    emp = Employee(jira_account_id=account_id, display_name="Заморозкин З.",
                   team=team, role="analyst")
    db_session.add(emp)
    db_session.commit()
    db_session.add(EmployeeTeam(employee_id=emp.id, team=team, is_primary=True,
                                joined_at=date(2026, 1, 1)))

    # Качество выпуска: 3 бага на 15 задач → 80,0
    released = []
    for i in range(15):
        issue = Issue(
            jira_issue_id=f"fz-rel-{i}", key=f"OS-{6000 + i}", summary="s", issue_type="Задача",
            status="ГОТОВО", status_category="done", resolution="Done",
            resolved_at=datetime(2026, 7, 10), project_id=project.id,
            reporter_account_id=account_id, team=team,
        )
        db_session.add(issue)
        released.append(issue)
    db_session.commit()
    for i in range(3):
        bug = Issue(
            jira_issue_id=f"fz-bug-{i}", key=f"OS-{6100 + i}", summary="s", issue_type="Баг",
            status="ГОТОВО", status_category="done", resolution="Done", environment="PROD",
            resolved_at=datetime(2026, 7, 12), project_id=project.id, team=team,
        )
        db_session.add(bug)
        db_session.commit()
        db_session.add(IssueLink(source_issue_id=bug.id, target_issue_id=released[i].id,
                                 link_type="Relates"))
    db_session.commit()

    # Соблюдение сроков: 1 из 1 в срок → 100,0
    db_session.add(Issue(
        jira_issue_id="fz-dl-1", key="OS-6200", summary="s", issue_type="Эпик",
        status="ГОТОВО", status_category="done", resolution="Done",
        resolved_at=datetime(2026, 7, 15, 10, 0), planned_end_date=datetime(2026, 7, 15, 0, 0),
        project_id=project.id, assignee_account_id=account_id, team=team,
    ))
    db_session.commit()

    live_before = build_report(db_session, [team], 2026, 7)
    row_before = next(r for r in live_before["rows"] if r["account_id"] == account_id)
    # Веса «Качество» (0,2) и «Сроки» (0,2) перенормированы между собой к
    # единице (регламенты/Cycle Time/оценка/трудозатраты — без данных):
    # 80*0,5 + 100*0,5 = 90,0.
    assert round(row_before["total"], 1) == 90.0

    payload = json.dumps(
        build_approval_payload(db_session, team, 2026, 7), ensure_ascii=False,
    )
    save_approval(db_session, team, 2026, 7, "Тестовый руководитель",
                 datetime(2026, 7, 30, 12, 0), payload)

    profile = db_session.query(KpiProfile).filter_by(code="analyst").one()
    quality_link = next(m for m in profile.metrics if m.metric.code == "quality")
    quality_link.weight = 0.9
    db_session.commit()

    # Живой пересчёт теперь даёт другое число — иначе тест не отличил бы
    # заморозку от случайного совпадения значений.
    live_after = build_report(db_session, [team], 2026, 7)
    row_after = next(r for r in live_after["rows"] if r["account_id"] == account_id)
    assert round(row_after["total"], 1) != round(row_before["total"], 1)

    frozen = report_with_approvals(db_session, [team], 2026, 7)
    frozen_row = next(r for r in frozen["rows"] if r["account_id"] == account_id)
    assert round(frozen_row["total"], 1) == round(row_before["total"], 1)
    assert frozen["approvals"][team]["approved"] is True


def test_kpi_section_hidden_by_default_via_ui_visibility(db_session):
    """Пункт 7 раздела 10: раздел не виден при выключенном признаке.

    Спека (раздел 7) сознательно не проверяет признак на сервере — это
    временное упрощение на время тестирования в отдельной ветке: сервер
    отвечает ``/kpi/*`` любому залогиненному без учёта роли, а видимость
    раздела в меню целиком регулируется общим списком скрытых разделов
    ``ui_hidden_section_keys`` (``app/api/endpoints/ui_config.py``), туда же
    маршрут ``/kpi`` дописывает миграция ``k09a_kpi_hidden_by_default``, чтобы
    после установки раздел был выключен «из коробки» (спека, раздел 1).
    CRUD над самим списком скрытых разделов для произвольных маршрутов уже
    полностью проверен в ``tests/test_ui_config_endpoint.py`` — здесь
    проверяется только то, что специфично для KPI: миграция реально
    добавляет ``/kpi`` в список по умолчанию.
    """
    import importlib.util
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    migration_path = repo_root / "alembic" / "versions" / "k09a_kpi_hidden_by_default.py"
    spec = importlib.util.spec_from_file_location("migration_k09a_kpi_hidden_by_default", migration_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)

    class _OpProxy:
        """Подменяет ``alembic.op`` реальным соединением тестовой БД для ``op.get_bind()``."""

        def __init__(self, connection):
            self._connection = connection

        def get_bind(self):
            return self._connection

    module.op = _OpProxy(db_session.connection())
    module.upgrade()
    db_session.commit()

    row = db_session.query(AppSetting).filter_by(key="ui_hidden_section_keys").one()
    hidden_keys = json.loads(row.value)
    assert "/kpi" in hidden_keys
