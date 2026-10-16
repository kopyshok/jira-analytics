"""Сотрудники базы ↔ пользователи новой Jira: списания, ФИО, конфликт «двое на одного»."""
from collections import Counter
from datetime import datetime

import pytest

from app.connectors.jira_client import (
    JiraAuthError,
    JiraClientError,
    JiraNetworkError,
    JiraRateLimitError,
    JiraServerError,
)
from app.services.jira_migration.fingerprints import DbWorklog, DcUser, DcWorklog, minute_of
from app.services.jira_migration.people import (
    STATUS_BY_HOURS,
    STATUS_BY_NAME,
    STATUS_DISPUTED,
    STATUS_NOT_FOUND,
    STATUS_SEARCH_FAILED,
    build_people_rows,
    classify_votes,
    exact_name_matches,
    finalize_people,
    normalize_name,
    vote_people,
)
from tests.services.jira_migration.factory import make_employee
from tests.services.jira_migration.fake_jira import FakeJira, dc_user

WALL = datetime(2026, 9, 10, 10, 0)
U5 = {"key": "JIRAUSER5", "name": "Ivanov_I", "display_name": "Иванов Иван"}


def _db(key: str, employee: str, shift: int = 0) -> DbWorklog:
    return DbWorklog(key, minute_of(WALL) + shift, 3600, employee, "Команда А")


def _dc(key: str, author: str, shift: int = 0) -> DcWorklog:
    return DcWorklog(key, minute_of(WALL) - 180 + shift, 3600, author)


def _row(employee: str, status: str, auto: dict | None = None, votes: int = 0,
         name: str | None = None) -> dict:
    return {
        "employee_id": employee, "display_name": name or employee, "worklogs": votes,
        "matched": votes, "status": status,
        "candidates": [{**auto, "votes": votes}] if auto else [], "auto": auto,
    }


def test_normalize_name():
    assert normalize_name("  Пётр   ПЕТРОВ ") == "петр петров"
    assert normalize_name("Ёлкин Иван") == "елкин иван"
    assert normalize_name(None) == ""


def test_votes_use_offset_and_unique_fingerprints_only():
    db_rows = [
        _db("OS-1", "e1"), _db("OS-1", "e1", 60), _db("OS-2", "e1"),
        _db("OS-3", "e1"), _db("OS-3", "e2"),   # одинаковые списания двух людей — не голос
    ]
    dc_rows = [
        _dc("OS-1", "U1"), _dc("OS-1", "U1", 60), _dc("OS-2", "U2"),
        _dc("OS-3", "U1"), _dc("OS-3", "U3"),
    ]
    assert vote_people(db_rows, dc_rows, offset_hours=3) == {"e1": Counter({"U1": 2, "U2": 1})}
    assert vote_people(db_rows, dc_rows, offset_hours=0) == {}


def test_classify_votes_thresholds():
    assert classify_votes(Counter({"U1": 9, "U2": 1})) == (STATUS_BY_HOURS, "U1")
    assert classify_votes(Counter({"U1": 8, "U2": 2})) == (STATUS_DISPUTED, None)
    assert classify_votes(Counter({"U1": 2})) == (STATUS_DISPUTED, None)
    assert classify_votes(Counter({"U1": 3})) == (STATUS_BY_HOURS, "U1")
    assert classify_votes(Counter()) == (None, None)
    assert classify_votes(None) == (None, None)


def test_exact_name_matches_without_partial():
    users = [
        DcUser("K1", "a", "Лебедев Александр"),
        DcUser("K2", "b", "Лебедев Александр Михайлович"),
        DcUser("K1", "a", "Лебедев Александр"),
    ]
    assert exact_name_matches("лебедев  александр", users) == [DcUser("K1", "a", "Лебедев Александр")]
    # порядок слов не важен: в базе «Имя Фамилия», в новой Jira «Фамилия Имя»
    assert exact_name_matches("Александр Лебедев", users) == [DcUser("K1", "a", "Лебедев Александр")]
    assert exact_name_matches("", users) == []


async def test_people_rows_by_hours_name_and_not_found(db_session):
    employees = [
        make_employee(db_session, f"cloud-{i}", name)
        for i, name in enumerate(
            ["Иванов Иван", "Петров Пётр", "Лебедев Александр", "Кузнецов Олег", "Сидоров Сидор",
             "Орлов Олег"]
        )
    ]
    ids = {e.display_name: e.id for e in employees}
    db_session.commit()
    jira = FakeJira(users=[
        dc_user("JIRAUSER7", "Petrov_P", "петров петр"),
        dc_user("JIRAUSER11", "Lebedev_A_A", "Лебедев Александр"),
        dc_user("JIRAUSER12", "Lebedev_A_M", "Лебедев Александр"),
        dc_user("JIRAUSER13", "Lebedev_A_A_M", "Лебедев Александр Михайлович"),
        dc_user("JIRAUSER14", "Orlov_O", "Орлов Олег", active=False),
    ])
    authors = {
        "JIRAUSER5": DcUser("JIRAUSER5", "Ivanov_I", "Иванов Иван"),
        "JIRAUSER6": DcUser("JIRAUSER6", "Ivanov_Old", "Иванов Иван"),
        "JIRAUSER8": DcUser("JIRAUSER8", "Kuznetsov_O", "Кузнецов Олег"),
    }
    votes = {ids["Иванов Иван"]: Counter({"JIRAUSER5": 4})}
    seen: list[int] = []

    rows = await build_people_rows(
        db_session, jira, votes, authors, {ids["Иванов Иван"]: 4}, on_progress=seen.append,
    )
    by_name = {r["display_name"]: r for r in rows}

    assert by_name["Иванов Иван"]["status"] == STATUS_BY_HOURS
    assert by_name["Иванов Иван"]["auto"] == U5
    assert (by_name["Иванов Иван"]["matched"], by_name["Иванов Иван"]["worklogs"]) == (4, 4)
    assert by_name["Петров Пётр"]["status"] == STATUS_BY_NAME
    assert by_name["Петров Пётр"]["auto"]["key"] == "JIRAUSER7"
    assert by_name["Лебедев Александр"]["status"] == STATUS_NOT_FOUND
    assert [c["key"] for c in by_name["Лебедев Александр"]["candidates"]] == ["JIRAUSER11", "JIRAUSER12"]
    # неактивный находится поиском, а кого нет в поиске — среди авторов списаний
    assert by_name["Орлов Олег"]["status"] == STATUS_BY_NAME
    assert by_name["Орлов Олег"]["auto"]["key"] == "JIRAUSER14"
    assert by_name["Кузнецов Олег"]["status"] == STATUS_BY_NAME
    assert by_name["Кузнецов Олег"]["auto"]["key"] == "JIRAUSER8"
    assert by_name["Сидоров Сидор"]["status"] == STATUS_NOT_FOUND
    assert by_name["Сидоров Сидор"]["candidates"] == []
    assert seen[-1] == 6
    # слова ищутся по очереди, пока не найдётся то же ФИО: поиск сравнивает начала слов
    searched = [arg for name, arg in jira.calls if name == "search_users"]
    assert sorted(searched) == ["Кузнецов", "Лебедев", "Олег", "Орлов", "Петров", "Сидор", "Сидоров"]


async def test_name_order_differs_in_db_and_new_jira(db_session):
    # в базе «Имя Фамилия», в новой Jira «Фамилия Имя»: первым словом ищется имя
    make_employee(db_session, "cloud-1", "Алексей Быстров")
    db_session.commit()
    jira = FakeJira(users=[
        dc_user("JIRAUSER7", "Bystrov_A", "Быстров Алексей"),
        dc_user("JIRAUSER8", "Bystrov_A_I", "Быстров Алексей Иванович"),
    ])

    rows = await build_people_rows(db_session, jira, {}, {}, {})

    assert rows[0]["status"] == STATUS_BY_NAME
    assert rows[0]["auto"]["key"] == "JIRAUSER7"
    assert [arg for name, arg in jira.calls if name == "search_users"] == ["Алексей"]


async def test_name_order_differs_among_worklog_authors(db_session):
    make_employee(db_session, "cloud-1", "Алексей Быстров")
    db_session.commit()
    author = DcUser("JIRAUSER7", "Bystrov_A", "Быстров Алексей")

    rows = await build_people_rows(db_session, FakeJira(), {}, {"JIRAUSER7": author}, {})

    assert (rows[0]["status"], rows[0]["auto"]["key"]) == (STATUS_BY_NAME, "JIRAUSER7")


async def test_surname_with_yo_is_also_searched_with_ye(db_session):
    # поиск новой Jira не приравнивает «ё» к «е»
    make_employee(db_session, "cloud-1", "Ёлкин  Иван")
    db_session.commit()
    jira = FakeJira(users=[dc_user("JIRAUSER7", "Elkin_I", "Елкин Иван")])

    rows = await build_people_rows(db_session, jira, {}, {}, {})

    assert rows[0]["status"] == STATUS_BY_NAME
    assert rows[0]["auto"]["key"] == "JIRAUSER7"
    assert [arg for name, arg in jira.calls if name == "search_users"] == ["Ёлкин", "Елкин"]


async def test_few_votes_for_one_user_confirmed_by_name(db_session):
    employee = make_employee(db_session, "cloud-1", "Иванов Иван")
    db_session.commit()
    ivanov = DcUser("JIRAUSER5", "Ivanov_I", "Иванов Иван")
    jira = FakeJira(users=[dc_user("JIRAUSER5", "Ivanov_I", "Иванов Иван")])

    rows = await build_people_rows(
        db_session, jira, {employee.id: Counter({"JIRAUSER5": 2})}, {"JIRAUSER5": ivanov}, {},
    )
    assert (rows[0]["status"], rows[0]["auto"], rows[0]["matched"]) == (STATUS_BY_NAME, U5, 2)
    assert rows[0]["candidates"] == [{**U5, "votes": 2}]

    other = FakeJira(users=[dc_user("JIRAUSER9", "Ivanov_New", "Иванов Иван")])
    rows = await build_people_rows(
        db_session, other, {employee.id: Counter({"JIRAUSER5": 2})}, {}, {},
    )
    assert rows[0]["status"] == STATUS_DISPUTED and rows[0]["auto"] is None

    split = FakeJira(users=[dc_user("JIRAUSER5", "Ivanov_I", "Иванов Иван")])
    rows = await build_people_rows(
        db_session, split, {employee.id: Counter({"JIRAUSER5": 1, "JIRAUSER6": 1})}, {}, {},
    )
    assert rows[0]["status"] == STATUS_DISPUTED
    assert split.calls == []


class _FailingSearch(FakeJira):
    def __init__(self, error: Exception, failing: set[str] | None = None) -> None:
        super().__init__()
        self.error = error
        self.failing = failing

    async def search_users(self, query: str, max_results: int = 20, include_inactive: bool = False) -> list:
        if self.failing is None or query in self.failing:
            raise self.error
        return await super().search_users(query, max_results, include_inactive)


async def test_failed_search_gets_own_status_and_note(db_session):
    make_employee(db_session, "cloud-1", "Петров Пётр")
    db_session.commit()

    rows = await build_people_rows(db_session, FakeJira(fail={"search_users"}), {}, {}, {})

    assert rows[0]["status"] == STATUS_SEARCH_FAILED
    outcome = finalize_people(rows, {})[rows[0]["employee_id"]]
    assert outcome.unresolved and outcome.key is None
    assert "Поиск" in outcome.note


@pytest.mark.parametrize("error", [
    JiraNetworkError("нет связи"), JiraServerError("503"), JiraAuthError("нет доступа"), JiraRateLimitError(60),
])
async def test_unavailable_jira_stops_people_step(db_session, error):
    make_employee(db_session, "cloud-1", "Петров Пётр")
    db_session.commit()

    with pytest.raises(type(error)):
        await build_people_rows(db_session, _FailingSearch(error), {}, {}, {})


async def test_five_failed_searches_in_a_row_stop_people_step(db_session):
    surnames = ["Альфа", "Бета", "Вега", "Гамма", "Дельта", "Жук", "Зубр", "Ива", "Кит"]
    for i, surname in enumerate(surnames):
        make_employee(db_session, f"cloud-{i}", f"{surname} Иван")
    db_session.commit()
    failing = set(surnames) - {"Дельта"}

    rows = await build_people_rows(db_session, _FailingSearch(RuntimeError("сбой"), failing), {}, {}, {})
    assert [r["status"] for r in rows].count(STATUS_SEARCH_FAILED) == 8

    make_employee(db_session, "cloud-last", "Лось Иван")
    db_session.commit()
    with pytest.raises(JiraClientError):
        await build_people_rows(
            db_session, _FailingSearch(RuntimeError("сбой"), failing | {"Лось"}), {}, {}, {},
        )


def test_finalize_auto_and_unresolved():
    rows = [_row("e1", STATUS_BY_HOURS, U5, 10), _row("e2", STATUS_DISPUTED), _row("e3", STATUS_NOT_FOUND)]
    out = finalize_people(rows, {})
    assert (out["e1"].key, out["e1"].source, out["e1"].unresolved) == ("JIRAUSER5", "auto", False)
    assert out["e2"].unresolved and out["e2"].key is None and out["e2"].note
    assert out["e3"].unresolved


def test_two_on_one_stronger_keeps_binding():
    rows = [_row("e1", STATUS_BY_HOURS, U5, 10, "Иванов Иван"),
            _row("e2", STATUS_BY_NAME, U5, 0, "Иванов И.")]
    out = finalize_people(rows, {})
    assert out["e1"].key == "JIRAUSER5" and not out["e1"].unresolved
    assert out["e2"].key is None and out["e2"].unresolved and out["e2"].source == "conflict"
    assert "Иванов Иван" in out["e2"].note


def test_two_on_one_tie_leaves_both_unresolved():
    out = finalize_people([_row("e1", STATUS_BY_NAME, U5), _row("e2", STATUS_BY_NAME, U5)], {})
    assert out["e1"].unresolved and out["e2"].unresolved
    assert out["e1"].key is None and out["e2"].key is None
    assert out["e1"].source == out["e2"].source == "conflict"


def test_decision_wins_conflict_and_unbind_resolves():
    rows = [_row("e1", STATUS_BY_HOURS, U5, 10, "Иванов Иван"),
            _row("e2", STATUS_NOT_FOUND, name="Иванов Второй")]
    out = finalize_people(rows, {"e2": {"action": "bind", **U5}, "e1": {"action": "unbind"}})
    assert (out["e2"].key, out["e2"].source, out["e2"].unresolved) == ("JIRAUSER5", "decision", False)
    assert out["e1"].key is None and not out["e1"].unresolved


def test_decision_takes_user_from_auto_binding():
    rows = [_row("e1", STATUS_BY_HOURS, U5, 10, "Иванов Иван"),
            _row("e2", STATUS_NOT_FOUND, name="Иванов Второй")]
    out = finalize_people(rows, {"e2": {"action": "bind", **U5}})
    assert out["e2"].key == "JIRAUSER5" and not out["e2"].unresolved
    assert out["e1"].unresolved and out["e1"].key is None and out["e1"].source == "conflict"


def test_two_decisions_on_one_user_are_unresolved():
    rows = [_row("e1", STATUS_NOT_FOUND), _row("e2", STATUS_NOT_FOUND)]
    out = finalize_people(rows, {"e1": {"action": "bind", **U5}, "e2": {"action": "bind", **U5}})
    assert out["e1"].unresolved and out["e2"].unresolved


def test_outcome_to_dict():
    out = finalize_people([_row("e1", STATUS_BY_HOURS, U5, 10)], {})
    assert out["e1"].to_dict() == {
        "key": "JIRAUSER5", "name": "Ivanov_I", "display_name": "Иванов Иван",
        "source": "auto", "unresolved": False, "note": None,
    }
