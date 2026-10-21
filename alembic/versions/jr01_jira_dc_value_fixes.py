"""jira_dc_value_fixes

Revision ID: jr01_jira_dc_value_fixes
Revises: em01_employee_account_aliases
Create Date: 2026-10-21

После переезда на Jira DC сменились значения, на которые ссылаются сохранённые
настройки: резолюция Done → «Готово»; статусы Отменено → Won't Do, К выполнению →
Сделать, Backlog → IDEA BACKLOG (+ APPROVED IDEA BACKLOG), Приостановлено → Hold;
вторым полем плановых часов QA при переезде выбрано «QA spent (ч)» — факт, а не
оценка. Правится только там, где найдено старое значение; повторный запуск ничего
не меняет. Самодостаточна: код приложения не импортирует.

Откат ничего не возвращает: старых значений в новой Jira нет, возвращать их в
настройки — снова сломать KPI и стол тимлида.
"""
import json
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "jr01_jira_dc_value_fixes"
down_revision: Union[str, None] = "em01_employee_account_aliases"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RESOLUTION_RENAMES = {"Done": "Готово"}
BACKLOG_STATUSES = {"Backlog", "Бэклог"}
BACKLOG_ADDITIONS = ["IDEA BACKLOG", "APPROVED IDEA BACKLOG"]
# Рядом со старым статусом (ключ) добавляются новые (значение).
DESK_ADDITIONS = {
    "Отменено": ["Won't Do"],
    "К выполнению": ["Сделать"],
    "Backlog": ["IDEA BACKLOG", "APPROVED IDEA BACKLOG"],
    "Приостановлено": ["Hold"],
}
DESK_LISTS = ("queue_statuses", "wip_statuses", "hidden_statuses")
EXCLUDED_ADDITIONS = {"Отменено": ["Won't Do"]}
QA_SPENT_FIELD = "customfield_10845"
QA_ESTIMATE_FIELD = "customfield_11042"
QA_ESTIMATE_NAME = "Оценка QA (ч)"

_settings = sa.table("app_settings", sa.column("key", sa.String), sa.column("value", sa.Text))
_metrics = sa.table(
    "kpi_metrics",
    sa.column("id", sa.String),
    sa.column("numerator_json", sa.Text),
    sa.column("denominator_json", sa.Text),
)


def _dedupe(values: list) -> list:
    out: list = []
    for v in values:
        if v not in out:
            out.append(v)
    return out


def _with_additions(values: list, additions: dict[str, list[str]]) -> list:
    out = list(values)
    for source, extra in additions.items():
        if source in out:
            out.extend(v for v in extra if v not in out)
    return out


def fix_status_list(values: list) -> list:
    return _with_additions(values, DESK_ADDITIONS)


def fix_metric_spec(spec: dict) -> bool:
    """Условия метрики KPI: Done → Готово, к исключению бэклога — новые бэклоги."""
    changed = False
    for cond in spec.get("conditions") or []:
        if not isinstance(cond, dict):
            continue
        attr, value = cond.get("attr"), cond.get("value")
        if attr == "resolution":
            if isinstance(value, list):
                new = _dedupe([RESOLUTION_RENAMES.get(v, v) for v in value])
            else:
                new = RESOLUTION_RENAMES.get(value, value)
            if new != value:
                cond["value"] = new
                changed = True
        elif (
            attr == "status" and cond.get("op") == "not_in"
            and isinstance(value, list) and BACKLOG_STATUSES & set(value)
        ):
            new = value + [s for s in BACKLOG_ADDITIONS if s not in value]
            if new != value:
                cond["value"] = new
                changed = True
    return changed


def fix_desk_config(cfg: dict) -> bool:
    changed = False
    groups = cfg.get("status_groups")
    if isinstance(groups, dict):
        for name, values in groups.items():
            if isinstance(values, list):
                new = fix_status_list(values)
                if new != values:
                    groups[name] = new
                    changed = True
    for key in DESK_LISTS:
        values = cfg.get(key)
        if isinstance(values, list):
            new = fix_status_list(values)
            if new != values:
                cfg[key] = new
                changed = True
    return changed


def fix_qa_setting(raw: str) -> str:
    """Поле плановых часов QA: «QA spent (ч)» → «Оценка QA (ч)» (список полей или одно поле)."""
    if not raw:
        return raw
    if raw.strip() == QA_SPENT_FIELD:
        return QA_ESTIMATE_FIELD
    try:
        items = json.loads(raw)
    except ValueError:
        return raw
    if not isinstance(items, list):
        return raw
    changed = False
    for item in items:
        if isinstance(item, dict) and item.get("field_id") == QA_SPENT_FIELD:
            item["field_id"] = QA_ESTIMATE_FIELD
            item["name"] = QA_ESTIMATE_NAME
            changed = True
    return json.dumps(items, ensure_ascii=False) if changed else raw


def _load_json(raw: Any) -> Any:
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


def _upgrade(conn: Any) -> None:
    for row in conn.execute(sa.select(_metrics)).mappings().all():
        updates = {}
        for col in ("numerator_json", "denominator_json"):
            spec = _load_json(row[col])
            if isinstance(spec, dict) and fix_metric_spec(spec):
                updates[col] = json.dumps(spec, ensure_ascii=False)
        if updates:
            conn.execute(_metrics.update().where(_metrics.c.id == row["id"]).values(**updates))

    settings = {key: value for key, value in conn.execute(sa.select(_settings.c.key, _settings.c.value))}

    def save(key: str, value: str) -> None:
        conn.execute(_settings.update().where(_settings.c.key == key).values(value=value))

    excluded = _load_json(settings.get("kpi_excluded_statuses"))
    if isinstance(excluded, list):
        new = _with_additions(excluded, EXCLUDED_ADDITIONS)
        if new != excluded:
            save("kpi_excluded_statuses", json.dumps(new, ensure_ascii=False))

    desk = _load_json(settings.get("team_desk_config"))
    if isinstance(desk, dict) and fix_desk_config(desk):
        save("team_desk_config", json.dumps(desk, ensure_ascii=False))

    qa_raw = settings.get("jira_planned_qa_hours_field_id")
    if qa_raw:
        new_qa = fix_qa_setting(qa_raw)
        if new_qa != qa_raw:
            save("jira_planned_qa_hours_field_id", new_qa)


def upgrade() -> None:
    _upgrade(op.get_bind())


def downgrade() -> None:
    pass
