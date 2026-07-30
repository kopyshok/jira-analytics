"""Excel-выгрузка отчёта KPI.

``openpyxl`` — ленивый импорт внутри функции, чтобы отсутствие библиотеки не
ломало импорт модуля (тот же приём, что в ``app/services/export_service.py``).
"""


def export_report_xlsx(report: dict) -> bytes:
    """Одна строка на человека: команда, метрики профиля (в порядке появления), итог."""
    from io import BytesIO

    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = f"KPI {report['year']}-{report['month']:02d}"[:31]

    rows = report.get("rows", [])
    metric_names: list[str] = []
    for row in rows:
        for m in row.get("metrics", []):
            if m["name"] not in metric_names:
                metric_names.append(m["name"])

    header = ["Команда", "Сотрудник"] + metric_names + ["Итого"]
    ws.append(header)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for row in rows:
        # Метрика без данных пишется словами, а не пустой ячейкой — иначе в
        # книге её не отличить от честного нуля (см. ревью, мелочи).
        by_metric = {m["name"]: m for m in row.get("metrics", [])}
        line: list = [row.get("team") or "", row["employee_name"]]
        for name in metric_names:
            m = by_metric.get(name)
            line.append(m["value"] if m and m["has_data"] else ("нет данных" if m else None))
        line.append(row.get("total"))
        ws.append(line)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
