"""LLM-провайдер интерфейс + factory.

Поддержка: Gemini (Google AI Studio), OpenRouter (десятки free-моделей).
"""
from typing import Protocol, runtime_checkable

from sqlalchemy.orm import Session

from app.services.llm.types import ProjectSummary


class ConfigurationError(Exception):
    """Провайдер не сконфигурирован (нет ключа)."""


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    model: str

    async def summarize_project(self, prompt: str, *, expect_json: bool = True) -> tuple[ProjectSummary, dict]:
        """Возвращает (parsed, meta) где meta содержит input_tokens / output_tokens / model."""
        ...

    async def healthcheck(self) -> bool:
        """Проверка соединения и ключа."""
        ...


def _get_app_setting(db: Session, key: str) -> str | None:
    """Минимальный helper — без зависимости от endpoints/settings.py."""
    from app.models.app_setting import AppSetting
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else None


def get_llm_provider(db: Session) -> LLMProvider:
    """Factory по AppSetting.llm_provider (default 'gemini')."""
    provider_name = (_get_app_setting(db, "llm_provider") or "gemini").lower()
    if provider_name == "gemini":
        from app.services.llm.gemini import GeminiProvider
        api_key = _get_app_setting(db, "llm_gemini_api_key")
        if not api_key:
            raise ConfigurationError("Gemini API key not configured")
        model = _get_app_setting(db, "llm_gemini_model")
        if model:
            return GeminiProvider(api_key=api_key, model=model)
        return GeminiProvider(api_key=api_key)
    if provider_name == "openrouter":
        from app.services.llm.openrouter import OpenRouterProvider
        api_key = _get_app_setting(db, "llm_openrouter_api_key")
        if not api_key:
            raise ConfigurationError("OpenRouter API key not configured")
        model = _get_app_setting(db, "llm_openrouter_model")
        fallback_csv = _get_app_setting(db, "llm_openrouter_fallback_models") or ""
        fallback_models = [m.strip() for m in fallback_csv.split(",") if m.strip()]
        kwargs: dict = {"api_key": api_key, "fallback_models": fallback_models}
        if model:
            kwargs["model"] = model
        return OpenRouterProvider(**kwargs)
    raise ConfigurationError(f"LLM provider '{provider_name}' not supported")
