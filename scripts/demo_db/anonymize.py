"""Обезличивание копии рабочей базы для демо-роликов.

Работает на сыром sqlite-соединении по отражённой схеме (sqlite_master / PRAGMA table_info),
поэтому покрывает и колонки, которых нет в моделях текущей ветки.

Порядок:
0. Сверка схемы с COLUMN_POLICY: каждая текстовая колонка каждой таблицы обязана быть
   объявлена (оставить / правило / очистить / только финальный проход). Неизвестная колонка
   (например, добавленная новой миграцией) — сборка падает, а не пропускает её молча.
1. Удалить таблицы целиком (кэши ИИ, обратная связь, статистика, история синхронизаций, столы),
   больничные (отсутствия и их снимки в сценариях); выключить расписания синхронизации.
2. Собрать исходные значения из структурных источников: люди, команды, группы, проекты,
   заказчики, направления, спринты, релизы, адрес Jira; хэши исходного свободного текста.
3. Словарь «настоящее → вымышленное» (детерминированный, вымышленное не содержит настоящих строк).
   Проекты получают буквы в перемешанном порядке, номера задач сдвигаются на число проекта.
4. Колоночные правила: заменить целиком / очистить свободный текст / секреты.
5. Финальный проход по всем текстовым колонкам всех таблиц: замена исходных строк словаря
   (самые длинные первыми, включая \\uXXXX-формы внутри JSON), фамилий отдельным словом
   в любой падежной форме и ключей задач KEY-123.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
import zlib
from dataclasses import dataclass, field
from itertools import count
from typing import Any, Callable, Iterable, Optional
from urllib.parse import urlsplit

from . import fake_data
from .leak_check import MIN_EXACT_LEN, exact_key, norm, trie_pattern, word_pattern

# Удаляются целиком: тексты ИИ, обратная связь, статистика использования, история
# синхронизаций с текстами ошибок, публичные рабочие столы (токены).
DELETE_TABLES = (
    "confluence_page_cache", "feedback_items", "project_ai_summaries", "work_type_report_snapshots",
    "executive_dashboard_snapshots", "issue_classifications", "usage_events", "usage_daily",
    "sync_run", "work_desks",
)

# Настройки: значение остаётся только у ключей из белого списка (номера полей Jira, настройки
# интерфейса и планирования, выбранная модель ИИ, даты перезагрузок). Остальное — пустая строка:
# учётные данные, адреса серверов, промпты и любые новые ключи.
SETTING_ALLOW_EXACT = frozenset({
    "ai_enabled", "llm_provider", "team_desk_config", "backfill_issue_author_done",
    "issues_reload_since_date", "worklog_reload_since_date",
})
SETTING_ALLOW_RE = re.compile(
    r"^(?:jira_[a-z0-9_]+_field_id|ui_[a-z0-9_]+|planning_[a-z0-9_]+|worklog_deadline_[a-z0-9_]+"
    r"|llm_[a-z0-9]+_model|llm_[a-z0-9]+_fallback_models)$"
)
# Второй замок: даже ключ из белого списка не сохраняется, если похож на секрет.
SECRET_SETTING_RE = re.compile(
    r"token|password|secret|api_key|apikey|credential|jira_email|confluence|prompt|login|username|sync_lock"
    r"|base_url|_url$|host",
    re.IGNORECASE,
)
JIRA_URL_SETTING = "jira_base_url"
DEMO_JIRA_URL = "https://jira.example.com"
DEMO_JIRA_HOST = "jira.example.com"

# Окружение задачи: остаются только стандартные названия стендов.
ENVIRONMENTS = frozenset({"dev", "test", "rc", "prod", "stage", "preprod"})
# Больничные удаляются целиком: причина отсутствия — сведения о здоровье.
SICK_REASON_CODES = frozenset({"sick", "sick_leave", "sickleave"})
SICK_LABEL_PREFIX = "больничн"

# Исходный свободный текст: его хэши — вход точной сверки в проверке утечек
# (значение не должно дословно оказаться ни в одной колонке демо-базы).
ORIGINAL_TEXT_COLUMNS = (
    ("issues", "summary"), ("issues", "description"), ("issues", "goal_text"),
    ("issues", "current_behavior"), ("issues", "impact"), ("issues", "risk"),
    ("comments", "body"), ("worklogs", "comment_text"),
    ("backlog_items", "title"), ("backlog_items", "impact"), ("backlog_items", "risk"),
    ("scenario_allocation_snapshots", "title"), ("scenario_allocation_snapshots", "impact"),
    ("scenario_allocation_snapshots", "risk"), ("scenario_revision_items", "backlog_item_name"),
    ("scenario_revisions", "note"), ("plan_audit", "comment"), ("plan_conflicts", "message"),
    ("team_desk_marks", "comment"), ("category_overrides", "comment"), ("projects", "description"),
    ("themes", "description"), ("scheduled_blocks", "reason"),
)

TEXT_TYPE_MARKERS = ("CHAR", "TEXT", "CLOB", "JSON")
# Колонки этих типов обязаны быть в COLUMN_POLICY (двоичные тоже: в них может лежать текст).
POLICY_TYPE_MARKERS = TEXT_TYPE_MARKERS + ("BLOB",)

KEEP, RULE, CLEAR, FINAL = "keep", "rule", "clear", "final"


def _parse_policy(spec: dict[str, str]) -> dict[str, dict[str, str]]:
    """«keep: a b; rule: c; clear: d» → {колонка: вид} для каждой таблицы."""
    out: dict[str, dict[str, str]] = {}
    for table, text in spec.items():
        cols = out.setdefault(table, {})
        for part in text.split(";"):
            kind, _, names = part.partition(":")
            kind = kind.strip()
            if kind not in (KEEP, RULE, CLEAR, FINAL):
                raise ValueError(f"COLUMN_POLICY[{table}]: неизвестный вид {kind!r}")
            for name in names.split():
                if name in cols:
                    raise ValueError(f"COLUMN_POLICY[{table}]: колонка {name} объявлена дважды")
                cols[name] = kind
    return out


# Политика по каждой текстовой колонке. keep — не чувствительно (идентификаторы, коды, справочники,
# настройки вида); rule — колоночное правило из _rules(); clear — очищается; final — свободный текст
# приложения, остаётся после финального прохода (замены словаря). Финальный проход и проверка утечек
# идут по всем колонкам независимо от вида. Таблицы из DELETE_TABLES очищаются целиком.
COLUMN_POLICY = _parse_policy({
    "alembic_version": "keep: version_num",
    "absence_reasons": "keep: id code label color",
    "absences": "keep: id employee_id reason_id",
    "app_settings": "keep: id key; rule: value",
    "backlog_items": "keep: id project_id issue_id planning_mode assignee_employee_id cost_type "
                     "developer_employee_id; rule: title customer assignee_jira_account_at_choice team; "
                     "clear: impact risk",
    "categories": "keep: id code label color work_type_id",
    "category_mappings": "keep: id entity_type entity_id category subcategory source_rule",
    "category_overrides": "keep: id category_code; rule: jira_issue_key; clear: comment",
    "comments": "keep: id jira_comment_id issue_id author_id; clear: body",
    "employee_capacity_overrides": "keep: id employee_id work_type_id",
    "employee_personal_normed": "keep: id setting_id work_type_id",
    "employee_personal_settings": "keep: id employee_id",
    "employee_subgroup_shares": "keep: id employee_id subgroup_id; rule: team",
    "employee_teams": "keep: id employee_id subgroup_id; rule: team",
    "employees": "keep: id role; rule: jira_account_id display_name email team; clear: avatar_url department",
    "hierarchy_rule": "keep: id issue_type; rule: project_key description",
    "involvement_defaults": "keep: id role; rule: team",
    "issue_links": "keep: id source_issue_id target_issue_id link_type",
    "issues": "keep: id jira_issue_id issue_type status status_category priority resolution subtype cost_type "
              "project_id parent_id category planned_hours_sources planned_hours_choice assigned_subgroup_id "
              "effective_subgroup_id assigned_category; "
              "rule: key summary environment direction sprint sprints release team participating_teams goals "
              "category_context category_context_key assignee_display_name assignee_account_id "
              "reporter_account_id reporter_display_name developer_account_id developer_display_name; "
              "clear: description goal_text current_behavior impact risk",
    "kpi_approvals": "keep: id; rule: team approved_by payload_json",
    "kpi_cycle_time_norms": "keep: id; rule: team",
    "kpi_metrics": "keep: id code name calc_kind fact_field score_fields empty_policy; "
                   "rule: numerator_json denominator_json; final: description",
    "kpi_profile_metrics": "keep: id profile_id metric_id",
    "kpi_profile_roles": "keep: id profile_id role_code",
    "kpi_profiles": "keep: id code name",
    "mandatory_work_types": "keep: id code label",
    "phase_predecessor": "keep: id successor_assignment_id predecessor_assignment_id",
    "plan_audit": "keep: id issue_id role source user_id; clear: comment",
    "plan_conflicts": "keep: id plan_id type severity status backlog_item_id employee_id assignment_id "
                      "detection_key; clear: message",
    "plan_item_dependencies": "keep: id plan_id from_item_id to_item_id dep_type source",
    "planning_scenarios": "keep: id quarter status; rule: name team",
    "production_calendar_day": "keep: kind note source",
    "projects": "keep: id jira_project_id project_type; rule: key name; clear: description",
    "release_notes": "keep: id version note_type section help_link created_by; final: title description",
    "resource_plan_assignments": "keep: id plan_id backlog_item_id phase employee_id daily_hours_json opo_part",
    "resource_plan_watch": "keep: id plan_id employee_id",
    "resource_plans": "keep: id scenario_id quarter status parent_plan_id; rule: team external_fingerprint; "
                      "final: label",
    "role_capacity_rules": "keep: id role work_type_id",
    "roles": "keep: id code label color",
    "scenario_absence_snapshots": "keep: id revision_id employee_id original_absence_id reason_id reason_label; "
                                  "rule: employee_name",
    "scenario_allocation_breakdown_snapshots": "keep: id revision_id allocation_id role employee_id",
    "scenario_allocation_snapshots": "keep: id revision_id allocation_id backlog_item_id issue_id project_id "
                                     "cost_type assignee_employee_id assignee_role_at_approval "
                                     "developer_employee_id; rule: title customer; clear: impact risk",
    "scenario_allocations": "keep: id scenario_id backlog_item_id",
    "scenario_calendar_snapshots": "keep: id revision_id kind",
    "scenario_capacity_snapshots": "keep: id revision_id employee_id; rule: employee_name",
    "scenario_dictionary_snapshots": "keep: id revision_id kind original_id code label extra_json",
    "scenario_norm_snapshots": "keep: id revision_id employee_id role work_type_id work_type_label; "
                               "rule: employee_name",
    "scenario_revision_items": "keep: id revision_id backlog_item_id action; rule: backlog_item_name",
    "scenario_revisions": "keep: id scenario_id parent_revision_id approved_by_user_id algo_version; clear: note",
    "scenario_rules": "keep: id scenario_id role work_type_id",
    "scenario_rules_snapshots": "keep: id revision_id role work_type_id work_type_label",
    "scenario_team_snapshots": "keep: id revision_id employee_id role; rule: display_name subgroup_name",
    "scheduled_block_employee": "keep: id block_id employee_id",
    "scheduled_block_role": "keep: id block_id role_id",
    "scheduled_blocks": "keep: id work_type_id; rule: team reason",
    "scope_projects": "keep: id jira_project_id; rule: jira_project_key",
    "scope_roots": "keep: id category_code jira_issue_id; rule: jira_issue_key project_key",
    "sync_schedule": "keep: id name cron_expr mode last_run_id; rule: team",
    "sync_state": "keep: id entity_name; rule: scope cursor_value; clear: last_error",
    "team_desk_daily_rates": "keep: id issue_id created_by_user_id",
    "team_desk_marks": "keep: id issue_id flag signature created_by_user_id; clear: comment",
    "team_onboarding_marks": "keep: id step state source marked_by_user_id; rule: team",
    "team_subgroups": "keep: id team_id; rule: name",
    "team_work_type_overrides": "keep: id backlog_item_id work_type_id; rule: team",
    "teams": "keep: id; rule: name",
    "themes": "keep: id work_type_id color created_by; rule: name; "
              "clear: description aliases_json embedding embedding_model_version embedding_updated_at",
    "user_rp_preferences": "keep: user_id collapsed_initiative_ids view_mode detail_sections_visible "
                           "detail_sections_collapsed",
    "users": "keep: id role selected_subgroups selected_period analytics_columns analytics_layout selected_theme "
             "appearance_settings last_seen_release_version onboarding; "
             "rule: email password_hash display_name default_team selected_teams team_desk_filter",
    "work_type_report_layouts": "keep: id user_id work_type_id grouping_dims_json visible_columns_json; rule: name",
    "worklog_quality_rules": "keep: id rule_code; final: description",
    "worklogs": "keep: id jira_worklog_id issue_id employee_id; clear: comment_text",
})
PUBLIC_EMAIL_DOMAINS = frozenset({
    "example.com", "gmail.com", "mail.ru", "yandex.ru", "ya.ru", "bk.ru", "list.ru", "inbox.ru",
    "rambler.ru", "outlook.com", "hotmail.com", "icloud.com",
})
# Хосты аватарок в ссылках (сами ссылки чистятся, это страховка проверки).
AVATAR_HOSTS = ("gravatar.com", "avatar-management")

# Колонки с именем человека рядом с учёткой Jira (учётка — главный признак личности).
ISSUE_PEOPLE = ("assignee", "reporter", "developer")
# Снимки сценариев: имя сотрудника рядом с employee_id.
SNAPSHOT_NAME_COLUMNS = (
    ("scenario_team_snapshots", "display_name"),
    ("scenario_capacity_snapshots", "employee_name"),
    ("scenario_norm_snapshots", "employee_name"),
    ("scenario_absence_snapshots", "employee_name"),
)
# JSON со списками команд (список или объект с ключом "teams").
TEAM_JSON_COLUMNS = (
    ("issues", "participating_teams"),
    ("users", "selected_teams"),
    ("users", "team_desk_filter"),
    ("executive_dashboard_snapshots", "team_set_json"),
    ("work_type_report_snapshots", "team_set_json"),
)

_ISSUE_KEY_RE = re.compile(r"^([A-Z][A-Z0-9_]*)-\d+$")
_NAME_SPLIT_RE = re.compile(r"[\s\-‐–—,.;()«»\"']+")
_PATRONYMIC_RE = re.compile(r"(вич|вна|чна|ьич)$")
_QUARTER_TAG_RE = re.compile(r"^\s*\d\s*кв\s*\d{2,4}\s*$", re.IGNORECASE)

Rule = Callable[[Any, dict], Any]


@dataclass
class Sensitive:
    """Исходные чувствительные строки — вход проверки утечек."""

    strings: frozenset[str]  # нормализованные (norm), ищутся подстрокой: ФИО, e-mail, команды, …
    project_keys: frozenset[str]  # настоящие ключи проектов: ищутся как KEY-123
    words: frozenset[str] = frozenset()  # падежные формы фамилий: ищутся отдельным словом
    originals: frozenset[bytes] = frozenset()  # хэши исходного свободного текста (leak_check.exact_key)
    primary_team: str = ""  # вымышленное имя основной команды
    stats: dict[str, int] = field(default_factory=dict)


def name_parts(name: str) -> tuple[Optional[str], list[str]]:
    """(ФИО для словаря или None, фамилии-кандидаты) в нормализованном виде.

    Порядок «Фамилия Имя» / «Имя Фамилия» в данных разный, поэтому фамилией считается
    любое слово от 5 букв, кроме известных имён и отчеств (не первым словом).
    Одиночное короткое слово или просто имя («тест», «Ольга») в словарь не идёт —
    иначе замена испортит обычные слова; такие значения заменяются колоночными правилами.
    """
    full = norm(name)
    tokens = [t for t in _NAME_SPLIT_RE.split(full) if t]
    surnames = [
        t for i, t in enumerate(tokens)
        if len(t) >= 5 and t not in fake_data.COMMON_FIRST_NAMES
        and not (i > 0 and _PATRONYMIC_RE.search(t))
    ]
    if len(tokens) >= 2 or (len(full) >= 5 and full not in fake_data.COMMON_FIRST_NAMES):
        return full, surnames
    return None, surnames


def surname_forms(token: str) -> set[str]:
    """Падежные формы фамилии (нормализованной): Боков → бокова, бокову, боковым, …

    Фамилия ищется отдельным словом во всех формах единственного числа, а не подстрокой:
    иначе «Новиков» находится в «черновиков», а «Боков» — в «боковая панель». Формы
    множественного числа (о семье) не берутся: «Черновых» совпадает с «черновых сценариях».
    """
    t = token
    if not re.fullmatch(r"[а-я]+", t):
        return {t}  # латиница и составные — без склонения
    if t.endswith(("ова", "ева", "ина", "ына")):
        stem, ends = t[:-1], ("а", "ой", "у", "ою")
    elif t.endswith(("ов", "ев", "ин", "ын")):
        stem, ends = t, ("", "а", "у", "ым", "ом", "е")
    elif t.endswith("ая"):
        stem, ends = t[:-2], ("ая", "ой", "ую", "ою")
    elif t.endswith(("ий", "ый", "ой")):
        stem, ends = t[:-2], (t[-2:], "ого", "ому", "им", "ым", "ом")
    elif t.endswith("а"):
        stem, ends = t[:-1], ("а", "ы", "и", "е", "у", "ой", "ою")
    elif t.endswith("я"):
        stem, ends = t[:-1], ("я", "и", "ю", "ей", "ею", "е")
    elif t.endswith("ь"):
        stem, ends = t[:-1], ("ь", "я", "ю", "ем", "е", "и")
    elif t[-1] in "оеиуюыэ":
        return {t}  # несклоняемые: Шевченко
    else:
        stem, ends = t, ("", "а", "у", "ом", "ым", "е")
    return {stem + e for e in ends}


def _is_placeholder(name: Any) -> bool:
    """Служебная подпись приложения в снимке без сотрудника, например «(внешний QA)»."""
    return isinstance(name, str) and name.strip().startswith("(") and name.strip().endswith(")")


def _person_key(name: str) -> str:
    """Ключ личности по имени: первые два слова без учёта порядка («Иванов Иван» = «Иван Иванов»)."""
    return " ".join(sorted(norm(name).split()[:2]))


def _escaped(text: str) -> str:
    return json.dumps(text, ensure_ascii=True)[1:-1]


def _str(value: Any) -> Optional[str]:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _is_sick(code: Any, label: Any) -> bool:
    return (_str(code) or "").lower() in SICK_REASON_CODES or norm(_str(label) or "").startswith(SICK_LABEL_PREFIX)


def _setting_allowed(key: str) -> bool:
    allowed = key in SETTING_ALLOW_EXACT or SETTING_ALLOW_RE.match(key) is not None
    return allowed and not SECRET_SETTING_RE.search(key)


class _Anonymizer:
    def __init__(self, conn: sqlite3.Connection, primary_team: str, password_hash: str) -> None:
        self.conn = conn
        self.primary_team = primary_team
        self.password_hash = password_hash
        self.cols = self._reflect()
        # Люди: личность = индекс; к ней привязаны учётки, варианты написания ФИО, e-mail.
        self.person_by_acc: dict[str, int] = {}
        self.person_by_key: dict[str, int] = {}
        self.person_by_email: dict[str, int] = {}
        self.person_surfaces: list[set[str]] = []
        self.fake_person: list[str] = []
        self.acc_map: dict[str, str] = {}
        self.email_map: dict[str, str] = {}
        self.emp_acc: dict[str, Optional[str]] = {}
        self.customers: list[str] = []
        # Команды, проекты и прочие справочники с настоящими названиями.
        self.teams: list[str] = []
        self.subgroups: list[str] = []
        self.project_keys: list[str] = []
        self.project_names: dict[str, str] = {}
        self.directions: list[str] = []
        self.sprints: list[str] = []
        self.releases: list[str] = []
        self.themes: list[str] = []
        self.hosts: set[str] = set()
        self.jira_host = ""
        self.category_codes: set[str] = set()
        self.backlog_issue: dict[str, Optional[str]] = {}
        self.originals: set[bytes] = set()
        self.dictionary_texts = 0  # исходных текстов, совпавших со справочниками (не сверяются)
        # Заполняются в build_fakes().
        self.maps: dict[str, dict[str, str]] = {}
        self.key_offset: dict[str, int] = {}
        self.titles: list[str] = []
        self.sensitive: set[str] = set()
        self.surname_words: set[str] = set()

    # --- схема и чтение ----------------------------------------------------------------

    def _reflect(self) -> dict[str, dict[str, tuple[str, bool]]]:
        tables = [r[0] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )]
        return {
            t: {r[1]: ((r[2] or "").upper(), bool(r[3])) for r in self.conn.execute(f"PRAGMA table_info({_q(t)})")}
            for t in tables
        }

    def _has(self, table: str, *cols: str) -> bool:
        return table in self.cols and all(c in self.cols[table] for c in cols)

    def _rows(self, table: str, cols: str) -> list[tuple]:
        names = cols.split()
        if not self._has(table, *names):
            return []
        select = ", ".join(_q(n) for n in names)
        return self.conn.execute(f"SELECT DISTINCT {select} FROM {_q(table)} ORDER BY {select}").fetchall()

    def _values(self, table: str, col: str) -> list[str]:
        return [v for (v,) in self._rows(table, col) if _str(v)]

    # --- 0. сверка схемы с политикой ------------------------------------------------------

    def check_policy(self) -> None:
        """Каждая текстовая (и двоичная) колонка каждой таблицы объявлена в COLUMN_POLICY."""
        missing = [
            f"{table}.{col}"
            for table, cols in self.cols.items() if table not in DELETE_TABLES
            for col, (typ, _) in cols.items()
            if (not typ or any(m in typ for m in POLICY_TYPE_MARKERS)) and col not in COLUMN_POLICY.get(table, {})
        ]
        if missing:
            raise RuntimeError(
                "Колонки без политики обезличивания — объявите их в COLUMN_POLICY (scripts/demo_db/anonymize.py): "
                + ", ".join(missing)
            )

    def check_primary_team(self) -> None:
        if not self._has("teams", "name") or self.primary_team not in self._values("teams", "name"):
            raise ValueError(f"Команды «{self.primary_team}» нет в справочнике команд (--primary-team)")

    # --- 1. удаление --------------------------------------------------------------------

    def delete_tables(self) -> None:
        for table in DELETE_TABLES:
            if table in self.cols:
                n = self.conn.execute(f"DELETE FROM {_q(table)}").rowcount
                print(f"  удалено {table}: {n}", flush=True)
        if self._has("sync_schedule", "last_run_id"):
            self.conn.execute("UPDATE sync_schedule SET last_run_id = NULL")
        if self._has("sync_schedule", "enabled"):
            self.conn.execute("UPDATE sync_schedule SET enabled = 0")
        sick = {rid for rid, code, label in self._rows("absence_reasons", "id code label") if _is_sick(code, label)}
        if self._has("absences", "reason_id"):
            n = sum(self.conn.execute("DELETE FROM absences WHERE reason_id = ?", (rid,)).rowcount for rid in sick)
            print(f"  удалено больничных: {n}", flush=True)
        if self._has("scenario_absence_snapshots", "reason_id", "reason_label"):
            rows = [
                (rowid,) for rowid, rid, label in self.conn.execute(
                    "SELECT rowid, reason_id, reason_label FROM scenario_absence_snapshots")
                if rid in sick or _is_sick(None, label)
            ]
            self.conn.executemany("DELETE FROM scenario_absence_snapshots WHERE rowid = ?", rows)
            print(f"  удалено больничных в снимках сценариев: {len(rows)}", flush=True)
        self.conn.commit()

    # --- 2. сбор исходных значений ------------------------------------------------------

    def _person(self, acc: Any, name: Any) -> Optional[int]:
        acc, name = _str(acc), _str(name)
        if not acc and not name:
            return None
        p = self.person_by_acc.get(acc) if acc else None
        key = _person_key(name) if name else None
        if p is None and key:
            p = self.person_by_key.get(key)
        if p is None:
            p = len(self.person_surfaces)
            self.person_surfaces.append(set())
        if acc:
            self.person_by_acc.setdefault(acc, p)
            self.acc_map.setdefault(acc, f"acc-{len(self.acc_map) + 1}")
        if name and key:
            self.person_by_key.setdefault(key, p)
            self.person_surfaces[p].add(name)
        return p

    def _email(self, email: Any, person: Optional[int]) -> None:
        email = _str(email)
        if not email:
            return
        low = email.lower()
        self.email_map.setdefault(low, f"user{len(self.email_map) + 1}@example.com")
        if person is not None:
            self.person_by_email.setdefault(low, person)

    @staticmethod
    def _add_unique(target: list[str], values: Iterable[Any]) -> None:
        seen = set(target)
        for v in values:
            if isinstance(v, str) and v.strip() and v not in seen:
                seen.add(v)
                target.append(v)

    @staticmethod
    def _json_teams(value: Any) -> list[str]:
        try:
            obj = json.loads(value)
        except (TypeError, ValueError):
            return []
        if isinstance(obj, dict):
            obj = obj.get("teams")
        return [t for t in obj if isinstance(t, str)] if isinstance(obj, list) else []

    def collect(self) -> None:
        # Люди: сотрудники первыми (у них учётка), затем поля ФИО задач, пользователи, снимки.
        employees = self._rows("employees", "display_name jira_account_id id email")
        for name, acc, emp_id, email in employees:
            p = self._person(acc, name)
            self.emp_acc[emp_id] = _str(acc)
            self._email(email, p)
        for role in ISSUE_PEOPLE:
            for acc, name in self._rows("issues", f"{role}_account_id {role}_display_name"):
                self._person(acc, name)
        for email, name in self._rows("users", "email display_name"):
            p = self.person_by_email.get((_str(email) or "").lower())
            if p is not None and _str(name):
                self.person_surfaces[p].add(_str(name))
                self.person_by_key.setdefault(_person_key(name), p)
            else:
                p = self._person(None, name)
            self._email(email, p)
        for table, col in SNAPSHOT_NAME_COLUMNS:
            for emp_id, name in self._rows(table, f"employee_id {col}"):
                if emp_id is None and _is_placeholder(name):
                    continue
                self._person(self.emp_acc.get(emp_id), name)
        for name in self._values("kpi_approvals", "approved_by"):
            self._person(None, name)
        for acc in self._values("backlog_items", "assignee_jira_account_at_choice"):
            self._person(acc, None)
        self._add_unique(self.customers, sorted(
            set(self._values("backlog_items", "customer")) | set(self._values("scenario_allocation_snapshots", "customer"))
        ))

        # Команды: основная первой, затем справочник команд, затем прочие имена из колонок
        # team/default_team и JSON (каждая группа по алфавиту).
        registry = set(self._values("teams", "name"))
        teams: set[str] = set(registry)
        for table, cols in self.cols.items():
            for col in ("team", "default_team"):
                if col in cols:
                    teams.update(self._values(table, col))
        for table, col in TEAM_JSON_COLUMNS:
            for value in self._values(table, col):
                teams.update(self._json_teams(value))
        for value in self._values("resource_plans", "external_fingerprint"):
            try:
                obj = json.loads(value)
            except ValueError:
                continue
            if isinstance(obj, dict):
                teams.update(k for k in obj if isinstance(k, str))
        for key, value in self._rows("app_settings", "key value"):
            if isinstance(key, str) and key.startswith("ui_") and "team" in key and _str(value):
                teams.update(t.strip() for t in value.split(",") if t.strip())
        teams = {t for t in teams if t.strip()}
        self._add_unique(self.teams, [self.primary_team] + sorted(registry) + sorted(teams - registry))

        self._add_unique(self.subgroups, self._values("team_subgroups", "name"))
        self._add_unique(self.subgroups, self._values("scenario_team_snapshots", "subgroup_name"))

        # Проекты: ключи из справочников и из ключей задач.
        keys: set[str] = set()
        for table, col in (("projects", "key"), ("scope_projects", "jira_project_key"),
                           ("hierarchy_rule", "project_key"), ("scope_roots", "project_key")):
            keys.update(v.strip() for v in self._values(table, col))
        for table, col in (("issues", "key"), ("issues", "category_context_key"),
                           ("scope_roots", "jira_issue_key"), ("category_overrides", "jira_issue_key")):
            for v in self._values(table, col):
                m = _ISSUE_KEY_RE.match(v.strip())
                if m:
                    keys.add(m.group(1))
        self.project_keys = sorted(keys)
        for key, name in self._rows("projects", "key name"):
            if _str(key) and _str(name):
                self.project_names[key.strip()] = name

        self._add_unique(self.directions, self._values("issues", "direction"))
        sprints = set(self._values("issues", "sprint"))
        for value in self._values("issues", "sprints"):
            try:
                obj = json.loads(value)
            except ValueError:
                continue
            if isinstance(obj, list):
                sprints.update(s for s in obj if isinstance(s, str) and s.strip())
        self._add_unique(self.sprints, sorted(sprints))
        self._add_unique(self.releases, self._values("issues", "release"))
        self._add_unique(self.themes, [
            r[0] for r in self.conn.execute("SELECT id FROM themes ORDER BY sort_order, name")
        ] if self._has("themes", "id", "sort_order", "name") else [])

        url = self.conn.execute(
            "SELECT value FROM app_settings WHERE key = ?", (JIRA_URL_SETTING,)
        ).fetchone() if self._has("app_settings", "key", "value") else None
        host = (urlsplit(url[0]).hostname or "").lower() if url and _str(url[0]) else ""
        if host:
            self.jira_host = host
            self.hosts.add(host)
            labels = host.split(".")
            org = labels[0] if host.endswith(".atlassian.net") else (labels[-2] if len(labels) >= 2 else "")
            if len(org) >= 4:
                self.hosts.add(org)
        for email in self.email_map:
            domain = email.rsplit("@", 1)[-1]
            if domain and domain not in PUBLIC_EMAIL_DOMAINS:
                self.hosts.add(domain)
                labels = domain.split(".")
                if len(labels) >= 2 and len(labels[-2]) >= 4:
                    self.hosts.add(labels[-2])

        self.category_codes = set(self._values("categories", "code"))
        self.backlog_issue = dict(self._rows("backlog_items", "id issue_id"))

        for table, col in ORIGINAL_TEXT_COLUMNS:
            if not self._has(table, col):
                continue
            for (value,) in self.conn.execute(
                f"SELECT {_q(col)} FROM {_q(table)} WHERE length({_q(col)}) >= ?", (MIN_EXACT_LEN,)
            ):
                key = exact_key(value) if isinstance(value, str) else None
                if key is not None:
                    self.originals.add(key)
        # Текст, дословно совпадающий со значением справочной колонки (статус «Проработка требований»,
        # вид работ «Технические задачи»), не секрет: он и так остаётся в демо-базе в этой колонке.
        dictionary: set[bytes] = set()
        for table, policy in COLUMN_POLICY.items():
            for col, kind in policy.items():
                if kind != KEEP or col == "id" or col.endswith("_id") or not self._has(table, col):
                    continue
                for (value,) in self.conn.execute(
                    f"SELECT DISTINCT {_q(col)} FROM {_q(table)} WHERE length({_q(col)}) >= ?", (MIN_EXACT_LEN,)
                ):
                    key = exact_key(value) if isinstance(value, str) else None
                    if key in self.originals:
                        dictionary.add(key)
        self.originals -= dictionary
        self.dictionary_texts = len(dictionary)

    # --- 3. словарь «настоящее → вымышленное» -------------------------------------------

    def _sensitive_tokens(self) -> tuple[set[str], set[str]]:
        """(строки для поиска подстрокой, формы фамилий для поиска словом)."""
        tokens: set[str] = set()
        words: set[str] = set()
        for name in [n for surfaces in self.person_surfaces for n in surfaces] + self.customers:
            full, surnames = name_parts(name)
            if full:
                tokens.add(full)
            for surname in surnames:
                words.update(surname_forms(surname))
        tokens.update(norm(e) for e in self.email_map)
        tokens.update(norm(a) for a in self.acc_map if len(a) >= 8)
        tokens.update(norm(t) for t in self.teams + self.subgroups if len(norm(t)) >= 4)
        tokens.update(norm(n) for n in self.project_names.values() if len(norm(n)) >= 4)
        tokens.update(norm(d) for d in self.directions if len(norm(d)) >= 5)
        tokens.update(self.hosts)
        tokens.add("atlassian.net")
        tokens.update(AVATAR_HOSTS)
        return tokens, words

    def build_fakes(self) -> tuple[dict[str, str], dict[str, str]]:
        """Словари финального прохода: (подстроки → вымышленное, формы фамилий → вымышленная фамилия)."""
        self.sensitive, self.surname_words = self._sensitive_tokens()
        # Вымышленное проверяется строже, чем база: формы фамилий — даже внутри слов.
        sens_re = re.compile(trie_pattern(self.sensitive | self.surname_words) or r"(?!)")

        def is_safe(text: str) -> bool:
            return not sens_re.search(norm(text)) and exact_key(text) not in self.originals

        names = fake_data.person_names(is_safe)
        self.fake_person = [next(names) for _ in self.person_surfaces]
        team_names = fake_data.team_names(is_safe)
        self.maps["team"] = {t: next(team_names) for t in self.teams}
        self.maps["subgroup"] = dict(zip(self.subgroups, fake_data.numbered("Группа", is_safe)))
        self.maps["customer"] = dict(zip(self.customers, fake_data.numbered("Заказчик", is_safe)))
        self.maps["direction"] = dict(zip(self.directions, fake_data.numbered("Направление", is_safe)))
        self.maps["sprint"] = dict(zip(self.sprints, fake_data.numbered("Спринт", is_safe)))
        self.maps["release"] = dict(zip(self.releases, fake_data.numbered("Релиз", is_safe)))
        self.maps["theme"] = dict(zip(self.themes, fake_data.numbered("Тема", is_safe)))
        # Буквы проектам — в перемешанном порядке (не по алфавиту настоящих ключей),
        # номера задач — со сдвигом на число проекта.
        order = fake_data.shuffled(self.project_keys)
        labels = (f"PR{fake_data.latin_label(i)}" for i in count())
        real = set(self.project_keys)
        free = (k for k in labels if k not in real and is_safe(k))
        self.maps["key"] = {k: next(free) for k in order}
        self.maps["project_name"] = {k: f"Проект {fake_data.ru_label(i)}" for i, k in enumerate(order)}
        self.key_offset = {k: fake_data.key_offset(fake) for k, fake in self.maps["key"].items()}
        self.titles = fake_data.issue_titles(is_safe)

        for label, fakes in [
            ("ФИО", self.fake_person), ("e-mail", self.email_map.values()), ("учётки", self.acc_map.values()),
            *[(k, v.values()) for k, v in self.maps.items()],
        ]:
            bad = [f for f in fakes if not is_safe(f)]
            if bad:
                raise RuntimeError(f"вымышленные значения ({label}) совпали с настоящими: {bad[:5]}")

        # Словарь финального прохода: ключи — norm(исходное), в т.ч. \\uXXXX-формы для JSON.
        repl: dict[str, str] = {}

        def add(original: str, fake: str) -> None:
            key = norm(original)
            if key in self.sensitive:
                repl.setdefault(key, fake)
                if not original.strip().isascii():
                    repl.setdefault(norm(_escaped(original.strip())), _escaped(fake))

        for p, surfaces in enumerate(self.person_surfaces):
            for name in sorted(surfaces):
                add(name, self.fake_person[p])
        for kind in ("team", "subgroup", "direction"):
            for original, fake in self.maps[kind].items():
                add(original, fake)
        for key, name in self.project_names.items():
            add(name, self.maps["project_name"][key])
        for original, fake in self.maps["customer"].items():
            add(original, fake)
        for original, fake in self.email_map.items():
            add(original, fake)
        for original, fake in self.acc_map.items():
            add(original, fake)
        # Адрес Jira → jira.example.com, прочие домены → example.com, имя организации → example.
        for host in sorted(self.hosts | {"atlassian.net", *AVATAR_HOSTS}):
            fake_host = DEMO_JIRA_HOST if host == self.jira_host else "example.com" if "." in host else "example"
            repl.setdefault(host, fake_host)
        # Фамилии отдельным словом (любая падежная форма) → вымышленная фамилия того же человека.
        word_repl: dict[str, str] = {}
        for p, surfaces in enumerate(self.person_surfaces):
            fake_surname = self.fake_person[p].split()[0]
            for name in sorted(surfaces):
                for token in name_parts(name)[1]:
                    for form in surname_forms(token):
                        word_repl.setdefault(form, fake_surname)
        for original, fake in self.maps["customer"].items():
            for token in name_parts(original)[1]:
                for form in surname_forms(token):
                    word_repl.setdefault(form, fake)

        missing = (self.sensitive - set(repl)) | (self.surname_words - set(word_repl))
        if missing:
            raise RuntimeError(f"нет замены для чувствительных строк: {sorted(missing)[:5]}")
        return repl, word_repl

    # --- 4. колоночные правила ----------------------------------------------------------

    def fake_name(self, acc: Any, name: Any) -> Any:
        if not _str(name):
            return name
        p = self.person_by_acc.get(_str(acc)) if _str(acc) else None
        if p is None:
            p = self.person_by_key.get(_person_key(name))
        if p is None:
            raise KeyError(f"ФИО не попало в словарь: {name!r}")
        return self.fake_person[p]

    def title_for(self, key: Any) -> str:
        return self.titles[zlib.crc32(str(key).encode()) % len(self.titles)]

    def fake_issue_key(self, project: str, number: str) -> str:
        """ROS-123 → PRC-(123 + сдвиг проекта)."""
        return f"{self.maps['key'][project]}-{int(number) + self.key_offset[project]}"

    def _clear(self, table: str, col: str) -> Rule:
        notnull = self.cols.get(table, {}).get(col, ("", False))[1]

        def rule(v: Any, _r: dict) -> Any:
            if v is None or not notnull:
                return None
            return "[]" if str(v).startswith("[") else "{}" if str(v).startswith("{") else ""
        return rule

    def _rules(self) -> dict[str, dict[str, Rule]]:
        """Правила колонок вида RULE. Колонки вида CLEAR очищаются по COLUMN_POLICY (apply_rules)."""
        maps = self.maps
        keys = self.maps["key"]
        key_alt = "|".join(sorted(map(re.escape, keys), key=len, reverse=True))
        issue_key_re = re.compile(rf"\b({key_alt})-(\d+)\b") if keys else None
        bare_key_re = re.compile(rf"\b({key_alt})\b") if keys else None
        quoted_key_re = re.compile(rf'"({key_alt})"') if keys else None
        clear = self._clear

        def mapped(kind: str) -> Rule:
            return lambda v, _r: maps[kind].get(v, v) if isinstance(v, str) else v

        def const(value: str) -> Rule:
            return lambda v, _r: value if _str(v) else v

        def acc(v: Any, _r: dict) -> Any:
            return self.acc_map.get(_str(v), v) if _str(v) else v

        def email(v: Any, _r: dict) -> Any:
            return self.email_map.get(_str(v).lower(), v) if _str(v) else v

        def person(acc_col: Optional[str]) -> Rule:
            return lambda v, r: self.fake_name(r.get(acc_col) if acc_col else None, v)

        def snapshot_person(v: Any, r: dict) -> Any:
            if r.get("employee_id") is None and _is_placeholder(v):
                return v
            return self.fake_name(self.emp_acc.get(r.get("employee_id")), v)

        def user_name(v: Any, r: dict) -> Any:
            p = self.person_by_email.get((_str(r.get("email")) or "").lower())
            return self.fake_person[p] if p is not None and _str(v) else self.fake_name(None, v)

        def issue_key(v: Any, _r: dict) -> Any:
            if not isinstance(v, str) or issue_key_re is None:
                return v
            return issue_key_re.sub(lambda m: self.fake_issue_key(m.group(1), m.group(2)), v)

        def bare_keys(v: Any, _r: dict) -> Any:
            if not isinstance(v, str) or bare_key_re is None:
                return v
            return bare_key_re.sub(lambda m: keys[m.group(1)], v)

        def quoted_keys(v: Any, _r: dict) -> Any:
            if not isinstance(v, str) or quoted_key_re is None:
                return v
            return quoted_key_re.sub(lambda m: f'"{keys[m.group(1)]}"', v)

        def project_key(v: Any, _r: dict) -> Any:
            return keys.get(v.strip(), v) if isinstance(v, str) else v

        def project_name(v: Any, r: dict) -> Any:
            return maps["project_name"].get(_str(r.get("key")) or "", v)

        def json_dump(obj: Any, original: str) -> str:
            return json.dumps(obj, ensure_ascii="\\u" in original)

        def team_json(v: Any, _r: dict) -> Any:
            try:
                obj = json.loads(v)
            except (TypeError, ValueError):
                return v
            if isinstance(obj, list):
                return json_dump([maps["team"].get(t, t) if isinstance(t, str) else t for t in obj], v)
            if isinstance(obj, dict) and isinstance(obj.get("teams"), list):
                obj["teams"] = [maps["team"].get(t, t) if isinstance(t, str) else t for t in obj["teams"]]
                return json_dump(obj, v)
            return v

        def team_keys_json(v: Any, _r: dict) -> Any:
            try:
                obj = json.loads(v)
            except (TypeError, ValueError):
                return v
            if not isinstance(obj, dict):
                return v
            return json_dump({maps["team"].get(k, k): val for k, val in obj.items()}, v)

        def sprint_json(v: Any, _r: dict) -> Any:
            try:
                obj = json.loads(v)
            except (TypeError, ValueError):
                return v
            if not isinstance(obj, list):
                return v
            return json.dumps([maps["sprint"].get(s, s) for s in obj], ensure_ascii=False)

        def issue_title(v: Any, r: dict) -> Any:
            return self.title_for(r["id"]) if _str(v) else v

        def linked_title(v: Any, r: dict) -> Any:
            issue_id = r.get("issue_id") or self.backlog_issue.get(r.get("backlog_item_id"))
            return self.title_for(issue_id or r.get("backlog_item_id") or r["id"]) if _str(v) else v

        def environment_or_clear(table: str, col: str) -> Rule:
            wipe = clear(table, col)
            return lambda v, r: v if not _str(v) or v.strip().casefold() in ENVIRONMENTS else wipe(v, r)

        def quarter_tags_or_clear(table: str, col: str) -> Rule:
            wipe = clear(table, col)
            return lambda v, r: v if not _str(v) or all(
                _QUARTER_TAG_RE.match(p) for p in v.split(",")) else wipe(v, r)

        def category_or_clear(table: str, col: str) -> Rule:
            wipe = clear(table, col)
            return lambda v, r: v if not _str(v) or v in self.category_codes else wipe(v, r)

        used_names: dict[str, int] = {}

        def scenario_name(v: Any, r: dict) -> Any:
            parts = [str(r.get("year") or ""), r.get("quarter") or "", maps["team"].get(r.get("team"), "")]
            base = " ".join(p for p in parts if p) or "Сценарий"
            used_names[base] = used_names.get(base, 0) + 1
            return base if used_names[base] == 1 else f"{base} ({used_names[base]})"

        def theme_name(v: Any, r: dict) -> Any:
            return maps["theme"].get(r["id"], v)

        def setting(v: Any, r: dict) -> Any:
            key = r.get("key") or ""
            if key == JIRA_URL_SETTING:
                return DEMO_JIRA_URL if _str(v) else v
            if _setting_allowed(key):
                return v
            return None if v is None else ""

        rules: dict[str, dict[str, Rule]] = {
            "employees": {"jira_account_id": acc, "display_name": person("jira_account_id"), "email": email},
            "users": {
                "email": email, "display_name": user_name, "password_hash": const(self.password_hash),
                "selected_teams": team_json, "team_desk_filter": team_json,
            },
            "issues": {
                "key": issue_key, "category_context_key": issue_key, "summary": issue_title,
                "environment": environment_or_clear("issues", "environment"),
                "goals": quarter_tags_or_clear("issues", "goals"),
                "category_context": category_or_clear("issues", "category_context"),
                "direction": mapped("direction"), "sprint": mapped("sprint"), "sprints": sprint_json,
                "release": mapped("release"), "participating_teams": team_json,
                **{f"{role}_account_id": acc for role in ISSUE_PEOPLE},
                **{f"{role}_display_name": person(f"{role}_account_id") for role in ISSUE_PEOPLE},
            },
            "category_overrides": {"jira_issue_key": issue_key},
            "scope_roots": {"jira_issue_key": issue_key, "project_key": project_key},
            "scope_projects": {"jira_project_key": project_key},
            "hierarchy_rule": {"project_key": project_key, "description": bare_keys},
            "projects": {"key": project_key, "name": project_name},
            "backlog_items": {
                "title": linked_title, "customer": mapped("customer"), "assignee_jira_account_at_choice": acc,
            },
            "scenario_allocation_snapshots": {"title": linked_title, "customer": mapped("customer")},
            "scenario_revision_items": {"backlog_item_name": linked_title},
            **{table: {col: snapshot_person} for table, col in SNAPSHOT_NAME_COLUMNS},
            "planning_scenarios": {"name": scenario_name},
            "resource_plans": {"external_fingerprint": team_keys_json},
            "scheduled_blocks": {"reason": const("Плановая блокировка")},
            "kpi_approvals": {"approved_by": person(None), "payload_json": quoted_keys},
            "kpi_metrics": {"numerator_json": quoted_keys, "denominator_json": quoted_keys},
            "teams": {"name": mapped("team")},
            "team_subgroups": {"name": mapped("subgroup")},
            "themes": {"name": theme_name},
            "sync_state": {"scope": bare_keys, "cursor_value": bare_keys},
            "app_settings": {"value": setting},
            "work_type_report_layouts": {"name": const("Раскладка")},
            **{table: {"team_set_json": team_json} for table in ("executive_dashboard_snapshots",
                                                                 "work_type_report_snapshots")},
        }
        rules["scenario_team_snapshots"]["subgroup_name"] = mapped("subgroup")
        # Любая колонка team / default_team — имя команды (в т.ч. в таблицах, неизвестных ветке).
        for table, cols in self.cols.items():
            for col in ("team", "default_team"):
                if col in cols:
                    rules.setdefault(table, {})[col] = mapped("team")
        return rules

    def _check_rules(self, rules: dict[str, dict[str, Rule]]) -> None:
        """Правила и COLUMN_POLICY согласованы: у каждой колонки вида RULE есть правило и наоборот."""
        bad = []
        for table, cols in self.cols.items():
            if table in DELETE_TABLES:
                continue
            policy = COLUMN_POLICY.get(table, {})
            for col in cols:
                has_rule = col in rules.get(table, {})
                if has_rule != (policy.get(col) == RULE):
                    bad.append(f"{table}.{col} ({policy.get(col) or 'не объявлена'}, правило: {has_rule})")
        if bad:
            raise RuntimeError("COLUMN_POLICY расходится с правилами: " + ", ".join(bad))

    def apply_rules(self) -> None:
        rules = self._rules()
        self._check_rules(rules)
        for table, policy in COLUMN_POLICY.items():
            for col, kind in policy.items():
                if kind == CLEAR:
                    rules.setdefault(table, {})[col] = self._clear(table, col)
        for table, table_rules in rules.items():
            cols = [c for c in table_rules if self._has(table, c)]
            if not cols:
                continue
            started = time.monotonic()
            names = list(self.cols[table])
            updates = []
            for row in self.conn.execute(f"SELECT rowid, * FROM {_q(table)}"):
                r = dict(zip(names, row[1:]))
                new = [table_rules[c](r[c], r) for c in cols]
                if any(n != r[c] for n, c in zip(new, cols)):
                    updates.append((*new, row[0]))
            sets = ", ".join(f"{_q(c)} = ?" for c in cols)
            self.conn.executemany(f"UPDATE {_q(table)} SET {sets} WHERE rowid = ?", updates)
            self.conn.commit()
            print(f"  {table}: {len(updates)} строк ({time.monotonic() - started:.1f} с)", flush=True)

    # --- 5. финальный проход ------------------------------------------------------------

    def final_pass(self, repl: dict[str, str], word_repl: dict[str, str]) -> dict[str, int]:
        pattern = re.compile(trie_pattern(repl, loose=True) or r"(?!)", re.IGNORECASE)
        words = re.compile(word_pattern(word_repl, loose=True) or r"(?!)", re.IGNORECASE)
        keys = self.maps["key"]
        key_alt = "|".join(sorted(map(re.escape, keys), key=len, reverse=True))
        key_re = re.compile(rf"\b({key_alt})-(\d+)\b") if keys else re.compile(r"(?!)")

        def scrub(text: str) -> str:
            text = pattern.sub(lambda m: repl.get(norm(m.group(0)), m.group(0)), text)
            text = words.sub(lambda m: word_repl.get(norm(m.group(0)), m.group(0)), text)
            return key_re.sub(lambda m: self.fake_issue_key(m.group(1), m.group(2)), text)

        changed: dict[str, int] = {}
        for table, cols in self.cols.items():
            if table == "alembic_version":
                continue
            text_cols = [c for c, (t, _) in cols.items() if not t or any(m in t for m in TEXT_TYPE_MARKERS)]
            if not text_cols:
                continue
            select = ", ".join(_q(c) for c in text_cols)
            updates = []
            for row in self.conn.execute(f"SELECT rowid, {select} FROM {_q(table)}"):
                values = row[1:]
                joined = "\x00".join(v for v in values if isinstance(v, str))
                if not joined or not (pattern.search(joined) or words.search(joined) or key_re.search(joined)):
                    continue
                new = [scrub(v) if isinstance(v, str) else v for v in values]
                if new != list(values):
                    updates.append((*new, row[0]))
                    for c, a, b in zip(text_cols, values, new):
                        if a != b:
                            changed[f"{table}.{c}"] = changed.get(f"{table}.{c}", 0) + 1
            if updates:
                sets = ", ".join(f"{_q(c)} = ?" for c in text_cols)
                self.conn.executemany(f"UPDATE {_q(table)} SET {sets} WHERE rowid = ?", updates)
                self.conn.commit()
        return changed


def anonymize(conn: sqlite3.Connection, *, primary_team: str, password_hash: str = "!") -> Sensitive:
    """Обезличить базу на месте. Возвращает исходные чувствительные строки для проверки утечек.

    password_hash — хэш, который получат все пользователи ("!" — вход невозможен).
    """
    conn.execute("PRAGMA foreign_keys = OFF")
    a = _Anonymizer(conn, primary_team, password_hash)
    a.check_policy()
    a.check_primary_team()
    print("Удаление таблиц…", flush=True)
    a.delete_tables()
    a.cols = a._reflect()
    print("Сбор исходных значений…", flush=True)
    a.collect()
    repl, word_repl = a.build_fakes()
    print(f"Словарь: {len(a.person_surfaces)} людей, {len(a.teams)} команд, {len(a.project_keys)} проектов, "
          f"{len(repl)} строк и {len(word_repl)} форм фамилий для замены, "
          f"{len(a.titles)} вариантов названий задач, {len(a.originals)} исходных текстов для сверки "
          f"(ещё {a.dictionary_texts} совпали со справочниками)", flush=True)
    print("Колоночные правила…", flush=True)
    a.apply_rules()
    print("Финальный проход по всем текстовым колонкам…", flush=True)
    changed = a.final_pass(repl, word_repl)
    for col, n in sorted(changed.items()):
        print(f"  {col}: {n}", flush=True)
    issues = conn.execute("SELECT count(*) FROM issues").fetchone()[0] if a._has("issues", "id") else 0
    return Sensitive(
        strings=frozenset(a.sensitive),
        project_keys=frozenset(a.project_keys),
        words=frozenset(a.surname_words),
        originals=frozenset(a.originals),
        primary_team=a.maps["team"].get(primary_team, ""),
        stats={
            "people": len(a.person_surfaces), "accounts": len(a.acc_map), "emails": len(a.email_map),
            "teams": len(a.teams), "subgroups": len(a.subgroups), "projects": len(a.project_keys),
            "customers": len(a.customers), "issues": issues,
        },
    )
