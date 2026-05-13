"""WorkTypeSynthesizer — Reduce-фаза + faithfulness retry → fallback."""
import pytest
from unittest.mock import AsyncMock

from app.services.llm.work_type_synthesizer import (
    WorkTypeSynthesizer, build_synthesis_prompt,
)


def _findings():
    return {
        "totals": {"hours": 540, "tasks": 78, "employees": 12},
        "themes": [{
            "id": "T1", "name": "Ошибки обмена",
            "hours": 173, "pct": 32, "tasks_count": 18, "employees_count": 5,
            "top_tasks": [{"key": "PROJ-321", "summary": "x", "hours": 86, "contribution": "разбор"}],
        }],
        "outliers": [{"key": "PROJ-321", "reason": "high_hours", "value": 86, "context": "..."}],
    }


@pytest.mark.asyncio
async def test_happy_path_returns_synthesis():
    fake = AsyncMock()
    fake.model = "m"
    fake.synthesize_work_type_report = AsyncMock(return_value=(
        {
            "headline": "540 ч сопровождения",
            "themes_narratives": [{"theme_id": "T1", "narrative": "см. PROJ-321", "evidence_keys": ["PROJ-321"]}],
            "outliers_explanations": [{"key": "PROJ-321", "explanation": "съела 86 ч"}],
            "recommendation": {"text": "rec", "expected_impact": "imp"},
        },
        {"model": "m", "input_tokens": 100, "output_tokens": 50},
    ))
    synth = WorkTypeSynthesizer(fake)
    out, meta = await synth.synthesize(_findings(), employee_names=set())
    assert out.is_fallback is False
    assert out.headline == "540 ч сопровождения"
    assert len(out.themes_narratives) == 1
    fake.synthesize_work_type_report.assert_called_once()


@pytest.mark.asyncio
async def test_faithfulness_failure_retries_then_falls_back():
    """First call returns hallucinated number, retry also fails → fallback narrative."""
    bad = {
        "headline": "9999 ч (галлюцинация)",
        "themes_narratives": [], "outliers_explanations": [],
        "recommendation": {"text": "", "expected_impact": ""},
    }
    fake = AsyncMock()
    fake.model = "m"
    fake.synthesize_work_type_report = AsyncMock(return_value=(bad, {"model": "m"}))
    synth = WorkTypeSynthesizer(fake)
    out, meta = await synth.synthesize(_findings(), employee_names=set())
    assert out.is_fallback is True
    assert "AI-сводка недоступна" in out.headline
    assert fake.synthesize_work_type_report.call_count == 2  # one retry


@pytest.mark.asyncio
async def test_provider_exception_returns_fallback_immediately():
    fake = AsyncMock()
    fake.model = "m"
    fake.synthesize_work_type_report = AsyncMock(side_effect=RuntimeError("LLM down"))
    synth = WorkTypeSynthesizer(fake)
    out, meta = await synth.synthesize(_findings(), employee_names=set())
    assert out.is_fallback is True
    assert "AI-сводка недоступна" in out.headline


def test_build_prompt_includes_totals_and_themes():
    p = build_synthesis_prompt(_findings())
    assert "540" in p
    assert "Ошибки обмена" in p
    assert "PROJ-321" in p
    assert "Не выдумывай" in p or "не выдумывай" in p.lower()


def test_build_prompt_strips_employee_names():
    """Имена сотрудников не должны попадать в промпт — LLM иначе их копирует.

    Faithfulness validator получает имена отдельно через employee_names.
    """
    findings = {
        "totals": {"hours": 100, "tasks": 5, "employees": 2},
        "themes": [{
            "theme_id": "T1", "name": "Тема",
            "totals": {"hours": 100, "pct": 100, "tasks_count": 5, "employees_count": 2},
            "by_employee": [
                {"employee_id": "e1", "name": "Пряничников Иван", "role": "ANALYST", "team": "T", "hours": 60},
                {"employee_id": "e2", "name": "Иванов Пётр", "role": "DEV", "team": "T", "hours": 40},
            ],
            "issues": [{
                "issue_id": "i1", "key": "PROJ-1", "summary": "x", "hours": 100,
                "employee_breakdown": [
                    {"name": "Пряничников Иван", "role": "ANALYST", "team": "T", "hours": 60},
                ],
            }],
        }],
    }
    p = build_synthesis_prompt(findings)
    assert "Пряничников" not in p
    assert "Иванов" not in p
