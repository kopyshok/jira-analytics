"""Настройки раздела «Рабочий стол тимлида».

Всё, что может измениться в Jira или в голове тимлида, — настройка в AppSetting,
а не константа в коде: статусная модель меняется, пороги подбираются на живых
данных.
"""
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import AppSetting

SETTING_KEY = "team_desk_config"

# Группы статусов. dev — мяч у разработчика, waiting — ждёт другого человека
# (тестировщика, аналитика, заказчика), todo — ещё не в работе, done — закрыта.
# В Jira у части статусов латинская «a»/«o» внутри русского слова — оба
# написания перечислены намеренно.
DEFAULT_STATUS_GROUPS: dict[str, list[str]] = {
    "dev": ["В РАБОТЕ", "КОД-РЕВЬЮ", "Ожидает помещения"],
    "waiting": [
        "ФИЧА-РЕВЬЮ",
        "Ожидает тестирования",
        "Тестирование",
        "У инициатора",
        "У инициаторa",
        "Ожидает обновления",
        "Ожидает oбновления",
    ],
    "todo": ["Backlog", "К выполнению", "Приостановлено"],
    "done": ["ГОТОВО", "Готово", "Отменено"],
}

DEFAULT_QUEUE_STATUSES = ["К выполнению", "В РАБОТЕ", "Ожидает помещения"]

# Статусы, в которых человек реально делает работу руками. Группа «у
# разработчика» шире: код-ревью и ожидание помещения мяч тоже держат за ним, но
# одновременной работой не являются — в лимите задач их считать нельзя.
DEFAULT_WIP_STATUSES = ["В РАБОТЕ"]

DEFAULT_THRESHOLDS: dict[str, float] = {
    "decomposition_hours": 16,   # оценка, с которой обязательна декомпозиция
    "overrun_pct": 30,           # перерасход от, %
    "underrun_pct": 50,          # недорасход от, %
    "stale_days": 5,             # зависла, дней в одном статусе
    "child_gap_pct": 25,         # оценки подзадач ниже родителя на, %
    "wip_limit": 3,              # лимит задач в работе одновременно
    "rubber_days": 5,            # «резиновая» задача: дней нормы в очередь
}

# Статусы, которых в разделе быть не должно вовсе: задача ещё не взята в
# работу, тимлиду смотреть на неё нечего. В счётчики и очередь тоже не идут.
DEFAULT_HIDDEN_STATUSES = ["Backlog"]

DEFAULT_SUBTASK_TYPES = ["Подзадача", "Sub-task"]
DEFAULT_ASSIGNEE_TYPES = ["Research"]
# Раздел — про разработчиков. Аналитики, РП и консультанты в срез не идут,
# даже если на них назначены задачи. Роль берётся из реестра ролей.
DEFAULT_DEVELOPER_ROLES = ["dev"]


@dataclass
class DeskConfig:
    status_groups: dict[str, list[str]] = field(default_factory=dict)
    queue_statuses: list[str] = field(default_factory=list)
    wip_statuses: list[str] = field(default_factory=list)
    hidden_statuses: list[str] = field(default_factory=list)
    thresholds: dict[str, float] = field(default_factory=dict)
    subtask_types: list[str] = field(default_factory=list)
    assignee_types: list[str] = field(default_factory=list)
    developer_roles: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status_groups": self.status_groups,
            "queue_statuses": self.queue_statuses,
            "wip_statuses": self.wip_statuses,
            "hidden_statuses": self.hidden_statuses,
            "thresholds": self.thresholds,
            "subtask_types": self.subtask_types,
            "assignee_types": self.assignee_types,
            "developer_roles": self.developer_roles,
        }


def defaults() -> DeskConfig:
    """Настройки по умолчанию — копия, её можно править не боясь глобалов."""
    return DeskConfig(
        status_groups={k: list(v) for k, v in DEFAULT_STATUS_GROUPS.items()},
        queue_statuses=list(DEFAULT_QUEUE_STATUSES),
        wip_statuses=list(DEFAULT_WIP_STATUSES),
        hidden_statuses=list(DEFAULT_HIDDEN_STATUSES),
        thresholds=dict(DEFAULT_THRESHOLDS),
        subtask_types=list(DEFAULT_SUBTASK_TYPES),
        assignee_types=list(DEFAULT_ASSIGNEE_TYPES),
        developer_roles=list(DEFAULT_DEVELOPER_ROLES),
    )


def load_config(db: Session) -> DeskConfig:
    """Настройки раздела; отсутствующие ключи добираются значениями по умолчанию."""
    cfg = defaults()
    row = db.query(AppSetting).filter(AppSetting.key == SETTING_KEY).first()
    if not row or not row.value:
        return cfg
    try:
        stored = json.loads(row.value)
    except (TypeError, ValueError):
        return cfg
    if not isinstance(stored, dict):
        return cfg

    if isinstance(stored.get("status_groups"), dict):
        for group, statuses in stored["status_groups"].items():
            if isinstance(statuses, list):
                cfg.status_groups[group] = [str(s) for s in statuses]
    for key in (
        "queue_statuses", "wip_statuses", "hidden_statuses",
        "subtask_types", "assignee_types", "developer_roles",
    ):
        if isinstance(stored.get(key), list):
            setattr(cfg, key, [str(s) for s in stored[key]])
    if isinstance(stored.get("thresholds"), dict):
        for key, value in stored["thresholds"].items():
            if key in cfg.thresholds:
                try:
                    cfg.thresholds[key] = float(value)
                except (TypeError, ValueError):
                    pass
    return cfg


def save_config(db: Session, cfg: DeskConfig) -> None:
    """Пишет настройки одной записью. Коммитит сам — как остальные сервисы."""
    row = db.query(AppSetting).filter(AppSetting.key == SETTING_KEY).first()
    payload = json.dumps(cfg.to_dict(), ensure_ascii=False)
    if row:
        row.value = payload
    else:
        db.add(AppSetting(id=str(uuid.uuid4()), key=SETTING_KEY, value=payload))
    db.commit()


def group_of_status(cfg: DeskConfig, status: Optional[str]) -> str:
    """dev | waiting | todo | done | unassigned.

    Статус, не отнесённый ни к одной группе, не ломает расчёты: он попадает
    в 'unassigned' и подсвечивается в настройках как нераспределённый.
    """
    if status is None:
        return "unassigned"
    for group, statuses in cfg.status_groups.items():
        if status in statuses:
            return group
    return "unassigned"
