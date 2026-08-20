"""Восемь признаков-проблем рабочего стола тимлида."""
from app.services.team_desk.config import defaults
from app.services.team_desk.flags import IssueFacts, compute_flags, flag_signature

CFG = defaults()


def facts(**kw) -> IssueFacts:
    base = dict(
        key="OS-1", status="В РАБОТЕ", group="dev", est=None, fact=0.0,
        days_in_status=0, child_est_sum=None, has_children=False,
        is_subtask=False, is_analysis=False,
    )
    base.update(kw)
    return IssueFacts(**base)


def test_overrun_when_fact_exceeds_estimate_by_threshold():
    assert "over" in compute_flags(facts(est=6, fact=9), CFG)
    assert "over" not in compute_flags(facts(est=6, fact=7), CFG)


def test_underrun_only_for_closed_issues():
    closed = facts(est=8, fact=0.5, status="Отменено", group="done")
    assert "under" in compute_flags(closed, CFG)
    assert "under" not in compute_flags(facts(est=8, fact=0.5), CFG)


def test_no_decomposition_above_threshold():
    assert "decomp" in compute_flags(facts(est=24), CFG)
    assert "decomp" not in compute_flags(facts(est=16), CFG)
    assert "decomp" not in compute_flags(
        facts(est=24, has_children=True, child_est_sum=24), CFG)


def test_child_gap_when_children_underestimated():
    assert "childgap" in compute_flags(
        facts(est=42, has_children=True, child_est_sum=0), CFG)
    assert "childgap" not in compute_flags(
        facts(est=40, has_children=True, child_est_sum=40), CFG)


def test_hours_on_not_started_issue():
    """Статус «не начата» + списанные часы = статус врёт."""
    idle = facts(est=6, fact=7, status="К выполнению", group="todo")
    assert "idlespent" in compute_flags(idle, CFG)
    # без часов признака нет, и в рабочем статусе — тоже
    assert "idlespent" not in compute_flags(
        facts(est=6, fact=0, status="К выполнению", group="todo"), CFG)
    assert "idlespent" not in compute_flags(facts(est=6, fact=7), CFG)
    # отметка сгорает, когда часы выросли или задачу сдвинули
    assert flag_signature("idlespent", idle) != flag_signature(
        "idlespent", facts(est=6, fact=9, status="К выполнению", group="todo"))


def test_missing_estimate_and_missing_worklog():
    assert compute_flags(facts(est=None), CFG) == ["noest"]
    assert "nospent" in compute_flags(facts(est=5, fact=0.0), CFG)
    assert "nospent" not in compute_flags(facts(est=5, fact=1.0), CFG)
    assert "nospent" not in compute_flags(
        facts(est=5, fact=0.0, status="ГОТОВО", group="done"), CFG)


def test_stale_only_for_open_issues():
    assert "stale" in compute_flags(facts(est=5, fact=1, days_in_status=6), CFG)
    assert "stale" not in compute_flags(
        facts(est=5, fact=5, days_in_status=99, status="ГОТОВО", group="done"), CFG)


def test_analysis_issue_skips_estimate_flags():
    got = compute_flags(facts(est=None, is_analysis=True, days_in_status=9), CFG)
    assert got == ["stale"]


def test_subtask_never_gets_decomposition_flags():
    got = compute_flags(facts(est=40, is_subtask=True), CFG)
    assert "decomp" not in got and "childgap" not in got


def test_flags_come_in_fixed_order():
    got = compute_flags(facts(est=6, fact=9, days_in_status=9), CFG)
    assert got == ["over", "stale"]


def test_signature_changes_with_cause():
    a = facts(est=6, fact=9, status="В РАБОТЕ", days_in_status=3)
    b = facts(est=6, fact=12, status="В РАБОТЕ", days_in_status=3)
    assert flag_signature("over", a) != flag_signature("over", b)
    assert flag_signature("stale", a) == flag_signature("stale", b)

    moved = facts(est=6, fact=9, status="КОД-РЕВЬЮ", days_in_status=1)
    assert flag_signature("stale", a) != flag_signature("stale", moved)


def test_signature_of_decomposition_follows_estimate():
    assert flag_signature("decomp", facts(est=24)) != flag_signature("decomp", facts(est=40))


def test_disabled_flag_is_not_computed():
    """Выключенный признак не считается вовсе — ни на строке, ни в счётчиках."""
    from dataclasses import replace

    cfg = replace(CFG, disabled_flags=["decomp"])
    assert "decomp" not in compute_flags(facts(est=24), cfg)
    # Остальные признаки той же задачи продолжают работать.
    assert "nospent" in compute_flags(facts(est=24), cfg)
