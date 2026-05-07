"""Faithfulness validator — числа и ключи задач из narrative должны быть в findings.

Защита от галлюцинаций LLM на Reduce-фазе тематического отчёта.
"""
import re
from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class FaithfulnessReport:
    ok: bool
    errors: list[str] = field(default_factory=list)


_NUM = re.compile(r"\b\d+(?:[.,]\d+)?\b")
_KEY = re.compile(r"\b[A-Z][A-Z0-9]{1,9}-\d+\b")


def _collect_numbers(findings: dict) -> set[float]:
    nums: set[float] = set()

    def walk(o: object) -> None:
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, (int, float)):
            nums.add(float(o))
    walk(findings)
    return nums


def _collect_keys(findings: dict) -> set[str]:
    keys: set[str] = set()

    def walk(o: object) -> None:
        if isinstance(o, str):
            for m in _KEY.findall(o):
                keys.add(m)
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(findings)
    return keys


def _extract_text(output: dict) -> str:
    parts: list[str] = []
    if h := output.get("headline"):
        parts.append(h)
    for tn in output.get("themes_narratives", []) or []:
        if t := tn.get("narrative"):
            parts.append(t)
    for oe in output.get("outliers_explanations", []) or []:
        if t := oe.get("explanation"):
            parts.append(t)
    rec = output.get("recommendation") or {}
    parts.append(rec.get("text", "") or "")
    parts.append(rec.get("expected_impact", "") or "")
    return "\n".join(parts)


def validate_synthesis(
    output: dict,
    findings: dict,
    employee_names: Iterable[str],
) -> FaithfulnessReport:
    """Проверить, что output не вышел за рамки findings.

    Числа сверяются с допуском ±10% (для округлений).
    Ключи задач — точное совпадение.
    Фамилии сотрудников запрещены.
    """
    text = _extract_text(output)
    errors: list[str] = []
    known_nums = _collect_numbers(findings)
    known_keys = _collect_keys(findings)

    # Build set of character spans covered by issue keys so we skip digits inside keys
    key_spans: set[int] = set()
    for m in _KEY.finditer(text):
        key_spans.update(range(m.start(), m.end()))

    for m in _NUM.finditer(text):
        if any(i in key_spans for i in range(m.start(), m.end())):
            continue  # digit is part of an issue key — not a standalone number
        n_str = m.group()
        try:
            n = float(n_str.replace(",", "."))
        except ValueError:
            continue
        # rounding tolerance ±10% (and at least ±0.5 for very small numbers)
        if not any(abs(n - kn) <= max(0.5, 0.10 * max(abs(n), abs(kn))) for kn in known_nums):
            errors.append(f"Unknown number {n_str} not in findings")

    for k in _KEY.findall(text):
        if k not in known_keys:
            errors.append(f"Unknown issue key {k} not in findings")

    for name in employee_names:
        if not name:
            continue
        surname = name.split()[0]
        if len(surname) > 3 and surname in text:
            errors.append(f"Employee name '{surname}' present in narrative (forbidden)")

    return FaithfulnessReport(ok=not errors, errors=errors)
