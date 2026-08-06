"""Excel-выгрузка отчёта KPI.

``openpyxl`` — ленивый импорт внутри функции, чтобы отсутствие библиотеки не
ломало импорт модуля (тот же приём, что в ``app/services/export_service.py``).
"""


def export_report_xlsx(report: dict) -> bytes:
    """Одна строка на человека: команда, метрики профиля (в порядке появления), итог.

    У периода длиннее месяца перед итогом появляются колонки помесячных
    значений — та же разбивка, что видна в ведомости на экране.
    """
    from io import BytesIO

    from openpyxl import Workbook
    from openpyxl.styles import Font

    months = report.get("months", 1) or 1
    wb = Workbook()
    ws = wb.active
    title = f"KPI {report['year']}-{report['month']:02d}"
    ws.title = (title if months == 1 else f"{title} за {months} мес")[:31]

    rows = report.get("rows", [])
    metric_names: list[str] = []
    for row in rows:
        for m in row.get("metrics", []):
            if m["name"] not in metric_names:
                metric_names.append(m["name"])

    # Колонки помесячной разбивки берутся у первой строки, где она есть:
    # период у всех строк отчёта один и тот же.
    breakdown = next((r.get("months_breakdown") for r in rows if r.get("months_breakdown")), []) or []
    month_cols = [f"{p['month']:02d}.{p['year']}" for p in breakdown]

    header = ["Команда", "Сотрудник"] + metric_names + month_cols + ["Итого"]
    ws.append(header)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for row in rows:
        # Метрика без данных пишется словами, а не пустой ячейкой — иначе в
        # книге её не отличить от честного нуля (см. ревью, мелочи).
        #
        # Значения округляются до целых процентов так же, как их показывает
        # интерфейс (``Math.round``) — иначе в книге попадает сырое число вида
        # 59.99999999999999 там, где на экране аккуратные 60% (см. находка 5).
        by_metric = {m["name"]: m for m in row.get("metrics", [])}
        line: list = [row.get("team") or "", row["employee_name"]]
        for name in metric_names:
            m = by_metric.get(name)
            line.append(round(m["value"]) if m and m["has_data"] else ("нет данных" if m else None))
        by_period = {
            f"{p['month']:02d}.{p['year']}": p.get("total") for p in row.get("months_breakdown") or []
        }
        for col in month_cols:
            value = by_period.get(col)
            line.append(round(value) if value is not None else None)
        total = row.get("total")
        line.append(round(total) if total is not None else None)
        ws.append(line)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
