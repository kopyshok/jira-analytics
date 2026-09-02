"""OmniRouteProvider — свой адрес сервиса, опциональный ключ, OpenAI-совместимый ответ."""
import pytest
from unittest.mock import AsyncMock, patch

from app.services.llm.omniroute import DEFAULT_BASE_URL, OmniRouteProvider
from app.services.llm.types import ProjectSummary


_SUMMARY_JSON = (
    '{"goals":["g1","g2","g3"],'
    '"result_checklist":[{"label":"x","done":true,"category":"analysis"}],'
    '"status_text":"OK","workload_summary":"WS",'
    '"work_breakdown":[{"bucket":"analysis","label":"Анализ","child_keys":["A-1"]}]}'
)


@pytest.mark.asyncio
async def test_summarize_uses_configured_base_url():
    provider = OmniRouteProvider(base_url="https://gw.example.com/v1/")
    fake_resp = {
        "choices": [{"message": {"content": _SUMMARY_JSON}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }
    post = AsyncMock(return_value=fake_resp)
    with patch.object(provider, "_post", post):
        summary, meta = await provider.summarize_project("test prompt")

    assert isinstance(summary, ProjectSummary)
    assert meta["model"] == "auto"
    assert post.await_args.args[0] == "https://gw.example.com/v1/chat/completions"


def test_defaults_are_keyless_and_local():
    provider = OmniRouteProvider()
    assert provider.base_url == DEFAULT_BASE_URL
    assert provider.model == "auto"
    # Без ключа заголовок авторизации не отправляется — шлюз работает открыто.
    assert "Authorization" not in provider._headers()
    assert "Authorization" in OmniRouteProvider(api_key="secret")._headers()
