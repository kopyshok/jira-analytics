"""Поля Jira при переезде: снимок облачных настроек, предложения, перезапись.

Номера полей в новой Jira другие. При первом пробном прогоне сохраняется
снимок облачных значений всех настроек полей — дальше он не меняется, даже
если администратор успел поправить настройки. Для каждого облачного поля
предлагается поле новой Jira с тем же названием; администратор подтверждает,
выбирает другое или ставит «не использовать». «Применить» переписывает
настройки из снимка по этому сопоставлению.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence, TypeGuard

from sqlalchemy.orm import Session

from app.models.app_setting import AppSetting
from app.services.jira_migration.cloud_fields import CLOUD_FIELD_NAMES
from app.services.plan_sources import Candidate, fingerprint, parse_field_setting

SNAPSHOT_KEY = "jira_migration_field_snapshot"
FIELD_SETTING_RE = re.compile(r"^jira_[a-z0-9_]+_field_id$")

# Настройки, которые сервис находит сам, если они пусты (синк — «Спринт»,
# «Ссылка на эпик», «Parent Link»; обновление бэклога — «Заказчик», «Тип
# затрат»). Без поля в новой Jira такие строки удаляются при применении.
AUTO_CACHE_KEYS = frozenset({
    "jira_sprint_field_id",
    "jira_customer_field_id",
    "jira_cost_type_field_id",
    "jira_epic_link_field_id",
    "jira_parent_link_field_id",
})

# Вовлечённость сервис из Jira больше не берёт: эти настройки нигде не читаются.
IGNORED_KEYS = frozenset({
    "jira_involvement_analyst_field_id",
    "jira_involvement_dev_field_id",
    "jira_involvement_qa_field_id",
    "jira_involvement_opo_field_id",
})

SETTING_LABELS: dict[str, str] = {
    "jira_team_field_id": "Команда задачи",
    "jira_participating_teams_field_id": "Участвующие команды",
    "jira_goals_field_id": "Цели (квартал)",
    "jira_goal_field_id": "Цель задачи",
    "jira_current_behavior_field_id": "Описание текущего поведения",
    "jira_planned_analyst_hours_field_id": "Плановые часы анализа",
    "jira_planned_dev_hours_field_id": "Плановые часы разработки",
    "jira_planned_qa_hours_field_id": "Плановые часы тестирования",
    "jira_planned_opo_hours_field_id": "Плановые часы ОПЭ",
    "jira_duration_analyst_field_id": "Длительность анализа",
    "jira_duration_dev_field_id": "Длительность разработки",
    "jira_duration_qa_field_id": "Длительность тестирования",
    "jira_duration_opo_field_id": "Длительность запуска",
    "jira_impact_field_id": "Влияние",
    "jira_risk_field_id": "Риск",
    "jira_rating_quality_field_id": "Оценка заказчика — качество",
    "jira_rating_speed_field_id": "Оценка заказчика — скорость",
    "jira_rating_result_field_id": "Оценка заказчика — результат",
    "jira_planned_start_date_field_id": "Плановая дата начала",
    "jira_planned_end_date_field_id": "Плановая дата окончания",
    "jira_environment_field_id": "Окружение",
    "jira_subtype_field_id": "Подтип",
    "jira_cost_type_field_id": "Тип затрат",
    "jira_cycle_time_field_id": "Фактический Cycle Time",
    "jira_direction_field_id": "Продуктовое направление",
    "jira_developer_field_id": "Разработчик",
    "jira_dev_est_field_id": "Оценка разработки (DEV est)",
    "jira_sprint_field_id": "Спринт",
    "jira_customer_field_id": "Заказчик",
    "jira_epic_link_field_id": "Ссылка на эпик",
    "jira_parent_link_field_id": "Ссылка на родителя (Parent Link)",
}
OTHER_LABEL = "Прочая настройка поля"


def read_field_settings(db: Session) -> dict[str, str]:
    """Текущие непустые значения настроек полей Jira (без неиспользуемых)."""
    out: dict[str, str] = {}
    rows = db.query(AppSetting.key, AppSetting.value).filter(AppSetting.key.startswith("jira_")).all()
    for key, value in rows:
        if not FIELD_SETTING_RE.match(key) or key in IGNORED_KEYS:
            continue
        if value and value.strip():
            out[key] = value.strip()
    return out


def load_field_snapshot(db: Session) -> dict[str, str]:
    raw = db.query(AppSetting.value).filter(AppSetting.key == SNAPSHOT_KEY).scalar()
    return json.loads(raw) if raw else {}


def ensure_field_snapshot(db: Session) -> dict[str, str]:
    """Снимок облачных значений: снимается при первом прогоне и дальше не меняется. Коммитит.

    Пустой снимок тоже остаётся: иначе настройки, заведённые уже под новую
    Jira, попали бы в снимок как облачные.
    """
    row = db.query(AppSetting).filter(AppSetting.key == SNAPSHOT_KEY).first()
    if row is not None:
        return json.loads(row.value) if row.value else {}
    snapshot = read_field_settings(db)
    db.add(AppSetting(key=SNAPSHOT_KEY, value=json.dumps(snapshot, ensure_ascii=False)))
    db.commit()
    return snapshot


def field_ids_of(raw: Optional[str]) -> list[str]:
    """Номера полей в значении настройки: строка или JSON-список плановых часов."""
    return [spec.field_id for spec in parse_field_setting(raw)]


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def suggest_dc_field(
    cloud_id: str,
    cloud_name: Optional[str],
    dc_fields: Sequence[Mapping[str, Any]],
) -> Optional[dict[str, str]]:
    """Поле новой Jira с тем же названием, что у облачного.

    Название сравнивается без учёта регистра и крайних пробелов, без
    частичных совпадений. Если одноимённых полей несколько, остаётся поле
    того же рода (своё против системного): «Окружение» есть и системное, и
    своё. Системное облачное поле, не найденное по названию (или без
    известного названия), ищется по тому же id: у системных полей он общий.
    """
    if cloud_name:
        wanted = _norm(cloud_name)
        same = [f for f in dc_fields if _norm(f.get("name")) == wanted]
        if len(same) > 1:
            is_custom = cloud_id.startswith("customfield_")
            same = [f for f in same if bool(f.get("custom")) == is_custom]
        if len(same) == 1:
            found = same[0]
            return {"id": str(found["id"]), "name": str(found.get("name") or found["id"])}
    if not cloud_id.startswith("customfield_"):
        for found in dc_fields:
            if found.get("id") == cloud_id:
                return {"id": str(found["id"]), "name": str(found.get("name") or found["id"])}
    return None


def build_field_rows(
    snapshot: Mapping[str, str],
    dc_fields: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Строка отчёта на каждое облачное поле из снимка: где используется и что предложено."""
    settings_by_field: dict[str, list[str]] = {}
    for key in sorted(snapshot):
        for field_id in field_ids_of(snapshot[key]):
            settings_by_field.setdefault(field_id, []).append(key)
    rows: list[dict[str, Any]] = []
    for cloud_id, keys in settings_by_field.items():
        name = CLOUD_FIELD_NAMES.get(cloud_id)
        suggestion = suggest_dc_field(cloud_id, name, dc_fields)
        rows.append({
            "cloud_id": cloud_id,
            "cloud_name": name,
            "settings": keys,
            "labels": [SETTING_LABELS.get(key, OTHER_LABEL) for key in keys],
            "suggested_id": suggestion["id"] if suggestion else None,
            "suggested_name": suggestion["name"] if suggestion else None,
            "auto_only": all(key in AUTO_CACHE_KEYS for key in keys),
        })
    rows.sort(key=lambda r: (r["cloud_name"] or r["cloud_id"]).lower())
    return rows


@dataclass
class FieldResolution:
    """Итог сопоставления полей."""

    mapping: dict[str, Optional[str]]  # облачный id → id новой Jira; None — не использовать
    names: dict[str, str]              # id новой Jira → название
    unresolved: list[str]              # облачные id, по которым нужно решение


def resolve_fields(
    rows: Sequence[Mapping[str, Any]],
    decisions: Mapping[str, Mapping[str, Any]],
    dc_fields: Sequence[Mapping[str, Any]],
) -> FieldResolution:
    """Решение администратора, иначе предложение по названию, иначе — нерешено.

    Поле, которое используется только автокэшами, нерешённым не считается:
    сервис найдёт его сам.
    """
    names = {str(f["id"]): str(f.get("name") or f["id"]) for f in dc_fields}
    mapping: dict[str, Optional[str]] = {}
    unresolved: list[str] = []
    for row in rows:
        cloud_id = row["cloud_id"]
        decision = decisions.get(cloud_id)
        if decision is not None:
            mapping[cloud_id] = decision.get("dc_field_id")
        elif row.get("suggested_id"):
            mapping[cloud_id] = row["suggested_id"]
        else:
            mapping[cloud_id] = None
            if not row.get("auto_only"):
                unresolved.append(cloud_id)
    return FieldResolution(mapping=mapping, names=names, unresolved=unresolved)


def rewrite_setting_value(
    raw: str,
    mapping: Mapping[str, Optional[str]],
    names: Mapping[str, str],
) -> str:
    """Значение настройки с полями новой Jira; поле «не использовать» выпадает.

    Пустая строка — настройка больше ни на что не указывает.
    """
    text = (raw or "").strip()
    if not text.startswith("["):
        new_id = mapping[text] if text in mapping else text
        return new_id or ""
    out: list[dict[str, str]] = []
    for spec in parse_field_setting(text):
        new_id = mapping[spec.field_id] if spec.field_id in mapping else spec.field_id
        if not new_id:
            continue
        out.append({
            "field_id": new_id,
            "kind": spec.kind,
            "name": names.get(new_id) or spec.name or new_id,
        })
    return json.dumps(out, ensure_ascii=False, separators=(",", ":")) if out else ""


def _is_number(value: Any) -> TypeGuard[float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def remap_plan_sources(
    sources: Optional[Mapping[str, Any]],
    choice: Optional[Mapping[str, Any]],
    mapping: Mapping[str, Optional[str]],
) -> tuple[Optional[dict], Optional[dict], bool]:
    """Кандидаты оценки и выбор при споре — с номерами полей новой Jira.

    Кандидат поля «не использовать» выбрасывается: следующий синк это поле
    уже не прочитает, и пересчитанный набор должен совпасть с тем, что он
    соберёт. Роль без кандидатов пропадает, пустой результат — ``None``
    (как в синке).

    Выбор, действовавший до переезда (его отпечаток совпадал с кандидатами),
    получает отпечаток пересчитанных кандидатов и остаётся действующим.
    Выбор выброшенного поля удаляется. Устаревший выбор не оживляется: его
    отпечаток не трогается. «sum» и «manual» — не номера полей, не меняются.

    Возвращает ``(кандидаты, выбор, выбор_сброшен)``: ``выбор_сброшен`` —
    у задачи удалён действовавший выбор хотя бы одной роли (спор придётся
    решать заново; отчёт считает такие задачи).
    """
    def dropped(source: Any) -> bool:
        return isinstance(source, str) and source in mapping and not mapping[source]

    def new_source(source: Any) -> Any:
        if isinstance(source, str) and mapping.get(source):
            return mapping[source]
        return source

    old_by_role: dict[str, list[Candidate]] = {}
    new_by_role: dict[str, list[Candidate]] = {}
    new_sources: Optional[dict] = None
    if sources:
        kept_sources: dict[str, list[Any]] = {}
        for role, items in sources.items():
            converted: list[Any] = []
            olds: list[Candidate] = []
            news: list[Candidate] = []
            for item in items or []:
                if not isinstance(item, Mapping):
                    converted.append(item)
                    continue
                source = item.get("source")
                label = item.get("label")
                value = item.get("value")
                amount = float(value) if isinstance(source, str) and _is_number(value) else None
                if amount is not None:
                    olds.append(Candidate(str(source), str(label or source), amount))
                if dropped(source):
                    continue
                target = new_source(source)
                new_label = target if label == source else label
                converted.append({**item, "source": target, "label": new_label})
                if amount is not None:
                    news.append(Candidate(str(target), str(new_label or target), amount))
            if converted:
                kept_sources[role] = converted
            old_by_role[role] = olds
            new_by_role[role] = news
        new_sources = kept_sources or None

    new_choice: Optional[dict] = None
    choice_dropped = False
    if choice:
        kept_choice: dict[str, Any] = {}
        for role, picked in choice.items():
            if not isinstance(picked, Mapping):
                kept_choice[role] = picked
                continue
            role_olds = old_by_role.get(role)
            in_force = bool(role_olds) and picked.get("fingerprint") == fingerprint(role_olds or [])
            if dropped(picked.get("source")):
                choice_dropped = choice_dropped or in_force
                continue
            updated = dict(picked)
            updated["source"] = new_source(picked.get("source"))
            if in_force:
                updated["fingerprint"] = fingerprint(new_by_role[role])
            kept_choice[role] = updated
        new_choice = kept_choice or None
    return new_sources, new_choice, choice_dropped
