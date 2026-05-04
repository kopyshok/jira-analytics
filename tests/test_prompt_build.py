from app.services.llm.prompt import build_prompt, PROMPT_VERSION


def test_prompt_uses_v3_base():
    assert PROMPT_VERSION.startswith("v3-")


def test_prompt_includes_full_8000_description():
    long_desc = "x" * 12000
    epic_data = {
        "key": "PRJ-1", "summary": "Эпик",
        "description": long_desc, "status": "In Progress",
        "is_done": False, "child_count": 0, "employee_count": 0,
        "total_hours": 0,
    }
    p = build_prompt(epic_data)
    assert "x" * 8000 in p
    assert "x" * 8001 not in p


def test_prompt_includes_child_extras():
    epic_data = {
        "key": "PRJ-1", "summary": "Эпик", "description": "", "status": "In Progress",
        "is_done": False, "child_count": 1, "employee_count": 1, "total_hours": 5,
        "child_summaries": [{
            "key": "PRJ-2", "summary": "Доработка",
            "description": "Технические детали ТЗ",
            "goal_text": "Цель аналитика",
            "current_behavior": "Сейчас не работает",
        }],
    }
    p = build_prompt(epic_data)
    assert "Технические детали ТЗ" in p
    assert "Цель аналитика" in p
    assert "Сейчас не работает" in p


def test_prompt_includes_confluence_pages():
    epic_data = {
        "key": "PRJ-1", "summary": "Эпик", "description": "", "status": "Done",
        "is_done": True, "child_count": 0, "employee_count": 0, "total_hours": 0,
        "confluence_pages": [{
            "title": "ТЗ полное", "url": "https://x/p/1",
            "body_text": "Содержимое спецификации",
        }],
    }
    p = build_prompt(epic_data)
    assert "ТЗ полное" in p
    assert "Содержимое спецификации" in p
