"""FaithfulnessValidator — числа и ключи задач должны быть в findings."""
from app.services.llm.faithfulness_validator import (
    validate_synthesis, FaithfulnessReport,
)


def test_clean_passes():
    findings = {
        "totals": {"hours": 540},
        "themes": [{"hours": 173, "pct": 32, "name": "X", "evidence_keys": ["PROJ-321"]}],
    }
    output = {
        "headline": "540 ч; X — 32% (PROJ-321)",
        "themes_narratives": [],
        "outliers_explanations": [],
        "recommendation": {"text": "x", "expected_impact": "y"},
    }
    rep = validate_synthesis(output, findings, employee_names={"Иванов И."})
    assert rep.ok and not rep.errors


def test_unknown_number_fails():
    findings = {"totals": {"hours": 540}, "themes": []}
    output = {
        "headline": "999 ч",
        "themes_narratives": [], "outliers_explanations": [],
        "recommendation": {"text": "", "expected_impact": ""},
    }
    rep = validate_synthesis(output, findings, employee_names=set())
    assert not rep.ok and any("999" in e for e in rep.errors)


def test_unknown_key_fails():
    findings = {"totals": {"hours": 540}, "themes": [{"evidence_keys": ["PROJ-1"]}]}
    output = {
        "headline": "ok",
        "themes_narratives": [{"theme_id": "t", "narrative": "see PROJ-9999 broken", "evidence_keys": []}],
        "outliers_explanations": [],
        "recommendation": {"text": "", "expected_impact": ""},
    }
    rep = validate_synthesis(output, findings, employee_names=set())
    assert not rep.ok


def test_employee_name_in_text_fails():
    findings = {"totals": {"hours": 100}, "themes": []}
    output = {
        "headline": "Иванов И. сделал больше всех",
        "themes_narratives": [], "outliers_explanations": [],
        "recommendation": {"text": "", "expected_impact": ""},
    }
    rep = validate_synthesis(output, findings, employee_names={"Иванов И.", "Петров П."})
    assert not rep.ok and any("Иванов" in e for e in rep.errors)


def test_rounding_within_10_pct_ok():
    findings = {"totals": {"hours": 540}, "themes": [{"pct": 32}]}
    output = {
        "headline": "около 30%",
        "themes_narratives": [], "outliers_explanations": [],
        "recommendation": {"text": "", "expected_impact": ""},
    }
    rep = validate_synthesis(output, findings, employee_names=set())
    # 30 ≈ 32 within 10% tolerance → pass
    assert rep.ok
