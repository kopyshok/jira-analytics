"""Сопоставление сотрудников базы с пользователями новой Jira.

1. По списаниям: голосуют совпавшие ворклоги (отпечаток, единственный с
   обеих сторон). Лидер ≥ 90 % голосов и ≥ 3 совпадений — «по списаниям»;
   иначе при совпадениях — «спорно». Если 1–2 совпавших списания указывают
   на одного пользователя и он же единственный с тем же ФИО — «по ФИО».
2. Без совпадений — по точному ФИО (регистр, ё→е, пробелы, порядок слов
   не важен: «Иван Петров» = «Петров Иван»; без частичных): ровно один
   пользователь новой Jira — «по ФИО».
3. Иначе — «не найден»: решает администратор; поиск не удался — «поиск не
   удался», тоже решает администратор.
Почта ненадёжна (облачная почта одного человека в новой Jira — у другого),
поэтому не используется.
"""
from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from app.connectors.jira_client import (
    JiraAuthError,
    JiraClientError,
    JiraNetworkError,
    JiraRateLimitError,
    JiraServerError,
)
from app.models import Employee
from app.services.jira_migration.fingerprints import DbWorklog, DcUser, DcWorklog
from app.services.jira_migration.store import PERSON_BIND

logger = logging.getLogger(__name__)

LEADER_SHARE = 0.9
LEADER_MIN_VOTES = 3
TOP_CANDIDATES = 5
# Поиск новой Jira сравнивает начала слов: по фамилии приходят и однофамильцы,
# и «Петрова», «Петровский» — предел с запасом, достигнут — предупреждение в лог.
NAME_SEARCH_LIMIT = 1000
MAX_SEARCH_FAILURES_IN_A_ROW = 5
# Нет доступа, лимит запросов, нет связи, сбой сервера — поиск по следующим
# сотрудникам тоже не удастся: прогон останавливается.
_FATAL_SEARCH_ERRORS = (JiraAuthError, JiraRateLimitError, JiraNetworkError, JiraServerError)

STATUS_BY_HOURS = "by_hours"
STATUS_BY_NAME = "by_name"
STATUS_DISPUTED = "disputed"
STATUS_NOT_FOUND = "not_found"
STATUS_SEARCH_FAILED = "search_failed"

SOURCE_AUTO = "auto"
SOURCE_DECISION = "decision"
SOURCE_NONE = "none"
SOURCE_CONFLICT = "conflict"

_NOTE_BY_STATUS = {
    STATUS_DISPUTED: "Совпавших списаний мало или они указывают на разных пользователей — "
                     "выберите нужного",
    STATUS_NOT_FOUND: "Нет совпадений ни по списаниям, ни по ФИО — выберите пользователя "
                      "или оставьте без привязки",
    STATUS_SEARCH_FAILED: "Поиск пользователя в новой Jira не удался — выберите пользователя "
                          "или запустите прогон заново",
}
NOTE_SHARED = "На одного пользователя новой Jira претендуют несколько сотрудников"


def normalize_name(value: Optional[str]) -> str:
    """ФИО для точного сравнения: регистр, ё→е, лишние пробелы."""
    return " ".join((value or "").lower().replace("ё", "е").split())


def name_key(value: Optional[str]) -> str:
    """Ключ ФИО без порядка слов: в базе бывает «Имя Фамилия», в новой Jira — «Фамилия Имя»."""
    return " ".join(sorted(normalize_name(value).split()))


def vote_people(
    db_rows: Sequence[DbWorklog],
    dc_rows: Sequence[DcWorklog],
    offset_hours: int,
) -> dict[str, Counter]:
    """Голоса «сотрудник базы → автор в новой Jira» по совпавшим ворклогам.

    Считаются только отпечатки, единственные с обеих сторон: два одинаковых
    списания (тот же час той же задачи) не говорят, чьё из них чьё.
    """
    shift = offset_hours * 60
    db_by_fp: dict[tuple[str, int, int], list[str]] = {}
    for row in db_rows:
        db_by_fp.setdefault((row.key, row.minute, row.seconds), []).append(row.employee_id)
    dc_by_fp: dict[tuple[str, int, int], list[str]] = {}
    for dc_row in dc_rows:
        dc_by_fp.setdefault(
            (dc_row.key, dc_row.minute + shift, dc_row.seconds), [],
        ).append(dc_row.author_key)
    votes: dict[str, Counter] = {}
    for fp, employees in db_by_fp.items():
        authors = dc_by_fp.get(fp)
        if authors is None or len(employees) != 1 or len(authors) != 1:
            continue
        votes.setdefault(employees[0], Counter())[authors[0]] += 1
    return votes


def classify_votes(votes: Optional[Counter]) -> tuple[Optional[str], Optional[str]]:
    """(«по списаниям» | «спорно» | None, ключ лидера). None — совпадений нет."""
    if not votes:
        return None, None
    total = sum(votes.values())
    leader, count = max(votes.items(), key=lambda item: (item[1], item[0]))
    if count >= LEADER_MIN_VOTES and count / total >= LEADER_SHARE:
        return STATUS_BY_HOURS, leader
    return STATUS_DISPUTED, None


def exact_name_matches(display_name: Optional[str], candidates: Iterable[DcUser]) -> list[DcUser]:
    """Пользователи с тем же ФИО (после нормализации, в любом порядке слов), без повторов, по ключу."""
    wanted = name_key(display_name)
    if not wanted:
        return []
    found: dict[str, DcUser] = {}
    for user in candidates:
        if name_key(user.display_name) == wanted and user.key not in found:
            found[user.key] = user
    return [found[key] for key in sorted(found)]


async def _search_by_name(jira: Any, display_name: Optional[str]) -> Optional[list[DcUser]]:
    """Пользователи новой Jira (и неактивные) по словам ФИО сотрудника; ``None`` — поиск не удался.

    Поиск новой Jira сравнивает начала слов и «ё» с «е» не приравнивает.
    Где фамилия — неизвестно (в базе бывает и «Имя Фамилия»), поэтому слова
    ищутся по очереди, пока среди найденных не окажется то же ФИО; слово с
    «ё» — ещё и написанием через «е». ФИО целиком сверяется потом. Нет
    доступа, лимит запросов, нет связи, сбой сервера — ошибка наружу:
    прогон останавливается.
    """
    words = (display_name or "").split()
    found: list[DcUser] = []
    failed = False
    queries = dict.fromkeys(q for w in words for q in (w, w.replace("ё", "е").replace("Ё", "Е")))
    for query in queries:
        if exact_name_matches(display_name, found):
            break
        try:
            users = await jira.search_users(query, max_results=NAME_SEARCH_LIMIT, include_inactive=True)
        except _FATAL_SEARCH_ERRORS:
            raise
        except Exception:  # noqa: BLE001 — сбой поиска по одному человеку не роняет прогон
            logger.warning("Поиск пользователей новой Jira по «%s» не удался", query, exc_info=True)
            failed = True
            continue
        if len(users) >= NAME_SEARCH_LIMIT:
            logger.warning(
                "Поиск пользователей новой Jira по «%s» упёрся в предел %d — часть однофамильцев "
                "могла не попасть в сверку ФИО", query, NAME_SEARCH_LIMIT,
            )
        found.extend(DcUser(u.jira_account_id, u.name, u.display_name) for u in users)
    return None if failed else found


def _candidate(user: DcUser, votes: int) -> dict[str, Any]:
    return {**user.to_dict(), "votes": votes}


async def build_people_rows(
    db: Session,
    jira: Any,
    votes: Mapping[str, Counter],
    authors: Mapping[str, DcUser],
    worklog_counts: Mapping[str, int],
    on_progress: Optional[Callable[[int], None]] = None,
) -> list[dict[str, Any]]:
    """Строка отчёта на каждого сотрудника базы.

    Кандидаты по ФИО — поиск пользователей новой Jira по фамилии (в том
    числе неактивных) и авторы ворклогов новой Jira. Поиск не удался у
    ``MAX_SEARCH_FAILURES_IN_A_ROW`` сотрудников подряд — ``JiraClientError``.
    Перед поиском коммитит: транзакция базы не висит открытой, пока идут
    запросы по каждому сотруднику.
    """
    authors_by_name: dict[str, list[DcUser]] = {}
    for user in authors.values():
        authors_by_name.setdefault(name_key(user.display_name), []).append(user)
    employees = db.query(Employee.id, Employee.display_name).order_by(Employee.display_name).all()
    db.commit()
    rows: list[dict[str, Any]] = []
    failures_in_a_row = 0
    for index, (employee_id, display_name) in enumerate(employees, start=1):
        counter = votes.get(employee_id) or Counter()
        status, leader = classify_votes(counter)
        candidates = [
            _candidate(authors.get(key) or DcUser(key, None, key), count)
            for key, count in counter.most_common(TOP_CANDIDATES)
        ]
        auto: Optional[dict[str, Any]] = None
        if status == STATUS_BY_HOURS and leader is not None:
            auto = (authors.get(leader) or DcUser(leader, None, leader)).to_dict()
        elif status is None or len(counter) == 1:
            # Совпадений нет — или их 1–2 и все за одного: сверка по ФИО.
            found = await _search_by_name(jira, display_name)
            if found is None:
                failures_in_a_row += 1
                if failures_in_a_row >= MAX_SEARCH_FAILURES_IN_A_ROW:
                    raise JiraClientError(
                        f"Поиск пользователей в новой Jira не удался {failures_in_a_row} раз подряд"
                    )
            else:
                failures_in_a_row = 0
            matches = exact_name_matches(
                display_name,
                [*(found or []), *authors_by_name.get(name_key(display_name), [])],
            )
            if status == STATUS_DISPUTED:
                if found is not None and len(matches) == 1 and matches[0].key in counter:
                    status = STATUS_BY_NAME
                    auto = matches[0].to_dict()
                    candidates = [_candidate(matches[0], counter[matches[0].key])]
            elif found is None:
                status = STATUS_SEARCH_FAILED
                candidates = [_candidate(user, 0) for user in matches]
            elif len(matches) == 1:
                status = STATUS_BY_NAME
                auto = matches[0].to_dict()
                candidates = [_candidate(matches[0], 0)]
            else:
                status = STATUS_NOT_FOUND
                candidates = [_candidate(user, 0) for user in matches]
        rows.append({
            "employee_id": employee_id,
            "display_name": display_name,
            "worklogs": int(worklog_counts.get(employee_id, 0)),
            "matched": sum(counter.values()),
            "status": status,
            "candidates": candidates,
            "auto": auto,
        })
        if on_progress is not None:
            on_progress(index)
    return rows


@dataclass(frozen=True)
class PersonOutcome:
    """Итоговая привязка сотрудника. ``key`` пуст — без привязки."""

    key: Optional[str]
    name: Optional[str]
    display_name: Optional[str]
    source: str
    unresolved: bool
    note: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _conflict_winner(
    members: list[str],
    result: Mapping[str, PersonOutcome],
    strength: Mapping[str, int],
) -> Optional[str]:
    decided = [m for m in members if result[m].source == SOURCE_DECISION]
    if len(decided) == 1:
        return decided[0]
    if decided:
        return None
    best = max(strength.get(m, 0) for m in members)
    leaders = [m for m in members if strength.get(m, 0) == best]
    return leaders[0] if len(leaders) == 1 else None


def finalize_people(
    rows: Sequence[Mapping[str, Any]],
    decisions: Mapping[str, Mapping[str, Any]],
) -> dict[str, PersonOutcome]:
    """Итоговая привязка каждого сотрудника с учётом решений администратора.

    Один пользователь новой Jira — не больше одного сотрудника. В конфликте
    «двое на одного» привязку сохраняет решение администратора, иначе
    сотрудник с большим числом совпавших списаний; остальные остаются без
    привязки (источник «конфликт») и ждут решения: другой пользователь или
    «без привязки». Слияния сотрудников нет.
    """
    result: dict[str, PersonOutcome] = {}
    strength: dict[str, int] = {}
    names = {row["employee_id"]: row.get("display_name") for row in rows}
    for row in rows:
        employee_id = row["employee_id"]
        decision = decisions.get(employee_id)
        if decision is not None:
            if decision.get("action") == PERSON_BIND:
                result[employee_id] = PersonOutcome(
                    decision["key"], decision.get("name"), decision.get("display_name"),
                    SOURCE_DECISION, False,
                )
            else:
                result[employee_id] = PersonOutcome(None, None, None, SOURCE_DECISION, False)
            continue
        auto = row.get("auto")
        if row.get("status") in (STATUS_BY_HOURS, STATUS_BY_NAME) and auto:
            result[employee_id] = PersonOutcome(
                auto["key"], auto.get("name"), auto.get("display_name"), SOURCE_AUTO, False,
            )
            strength[employee_id] = next(
                (c.get("votes", 0) for c in row.get("candidates", []) if c.get("key") == auto["key"]), 0,
            )
        else:
            result[employee_id] = PersonOutcome(
                None, None, None, SOURCE_NONE, True, _NOTE_BY_STATUS.get(row.get("status") or ""),
            )

    by_key: dict[str, list[str]] = {}
    for employee_id, outcome in result.items():
        if outcome.key:
            by_key.setdefault(outcome.key, []).append(employee_id)
    for members in by_key.values():
        if len(members) < 2:
            continue
        winner = _conflict_winner(members, result, strength)
        for employee_id in members:
            if employee_id == winner:
                continue
            note = (
                f"Этот пользователь новой Jira уже привязан к сотруднику «{names.get(winner)}»"
                if winner is not None else NOTE_SHARED
            )
            result[employee_id] = PersonOutcome(None, None, None, SOURCE_CONFLICT, True, note)
    return result
