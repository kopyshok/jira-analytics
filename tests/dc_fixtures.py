"""Обезличенные ответы Jira DC для тестов (генерирует scripts/make_dc_fixtures.py)."""
import json
from pathlib import Path
from typing import Any

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "jira_dc"


def load_dc(name: str) -> Any:
    """Прочитать фикстуру ``tests/fixtures/jira_dc/<name>`` свежей копией."""
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))
