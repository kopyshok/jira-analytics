"""OmniRoute provider — внутренний AI-шлюз (self-hosted).

Endpoint: <base_url>/chat/completions (OpenAI-compat, как у DeepSeek).
Base URL задаётся в настройках, дефолт — локальная установка из документации.
Ключ опционален: свежая установка OmniRoute отвечает без авторизации.

Модели: `auto` (балансировка), `auto/coding`, `auto/cheap`, либо
`провайдер/модель` напрямую. Роутингом между провайдерами занимается сам
шлюз, поэтому цепочка fallback-моделей на нашей стороне не нужна.
"""
from app.services.llm.deepseek import DeepSeekProvider


DEFAULT_BASE_URL = "http://localhost:20128/v1"
_DEFAULT_MODEL = "auto"


class OmniRouteProvider(DeepSeekProvider):
    name = "omniroute"

    def __init__(
        self,
        api_key: str = "",
        model: str = _DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        super().__init__(api_key=api_key, model=model, base_url=base_url or DEFAULT_BASE_URL)
