"""LLM administration: test connection, regenerate-all, list models."""
import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.jobs.regenerate_summaries import regenerate_outdated_summaries
from app.services.llm.base import ConfigurationError, get_llm_provider
from app.services.llm.prompt import DEFAULT_SYSTEM_ROLE, FORMAT_SPEC
from app.models.app_setting import AppSetting


router = APIRouter()


@router.post("/test")
async def test_connection(db: Session = Depends(get_db)):
    """Проверка соединения с настроенным LLM-провайдером."""
    try:
        provider = get_llm_provider(db)
    except ConfigurationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    ok = await provider.healthcheck()
    return {"ok": ok, "provider": provider.name, "model": provider.model}


@router.post("/regenerate-all")
async def regenerate_all(background: BackgroundTasks):
    """Запускает в background регенерацию всех устаревших AI-саммари."""
    background.add_task(regenerate_outdated_summaries)
    return {"started": True}


@router.get("/prompt-default")
async def get_prompt_default():
    """Дефолтный текст системного промпта (роль/тон) + read-only описание формата.

    `system_role` — редактируется пользователем через AppSetting
    `llm_project_summary_system_prompt`. `format_spec` — хардкод JSON-схемы,
    нельзя менять без правки backend-схемы.
    """
    return {"system_role": DEFAULT_SYSTEM_ROLE, "format_spec": FORMAT_SPEC}


# Префиксы моделей, не подходящих для текстового AI-саммари
_GEMINI_EXCLUDE_KEYWORDS = (
    "tts", "image", "robotics", "computer-use", "embedding",
    "lyria", "nano-banana", "gemma", "deep-research",
)


@router.get("/gemini/models")
async def list_gemini_models(db: Session = Depends(get_db)):
    """Живой список доступных Gemini-моделей из Google API.

    Фильтр: только generateContent + текстовые (без TTS/image/embedding/robotics).
    Возвращает массив `{id, label, version}` отсортированный по version desc.
    """
    row = db.query(AppSetting).filter(AppSetting.key == "llm_gemini_api_key").first()
    if not row or not row.value:
        raise HTTPException(status_code=400, detail="Gemini API key not configured")

    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={row.value}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=503, detail=f"Google API ответил {e.response.status_code}")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Google API недоступен: {e}")

    out: list[dict] = []
    for m in data.get("models", []):
        methods = m.get("supportedGenerationMethods", [])
        if "generateContent" not in methods:
            continue
        name = m.get("name", "")  # "models/gemini-3.1-flash-lite-preview"
        model_id = name.removeprefix("models/")
        lower = model_id.lower()
        if any(kw in lower for kw in _GEMINI_EXCLUDE_KEYWORDS):
            continue
        out.append({
            "id": model_id,
            "label": m.get("displayName", model_id),
            "version": _gemini_version_key(model_id),
        })
    out.sort(key=lambda x: (-x["version"], x["id"]))
    return out


@router.get("/openrouter/models")
async def list_openrouter_models(db: Session = Depends(get_db)):
    """Список бесплатных моделей OpenRouter (pricing.prompt == 0 AND completion == 0).

    Сортировка: context_length desc. Возвращает `{id, label, context_length}`.
    """
    row = db.query(AppSetting).filter(AppSetting.key == "llm_openrouter_api_key").first()
    if not row or not row.value:
        raise HTTPException(status_code=400, detail="OpenRouter API key not configured")

    url = "https://openrouter.ai/api/v1/models"
    headers = {"Authorization": f"Bearer {row.value}"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=503, detail=f"OpenRouter API ответил {e.response.status_code}")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"OpenRouter API недоступен: {e}")

    out: list[dict] = []
    for m in data.get("data", []):
        pricing = m.get("pricing") or {}
        prompt_price = str(pricing.get("prompt", "0"))
        completion_price = str(pricing.get("completion", "0"))
        if not (_is_zero(prompt_price) and _is_zero(completion_price)):
            continue
        model_id = m.get("id", "")
        if not model_id:
            continue
        out.append({
            "id": model_id,
            "label": m.get("name", model_id),
            "context_length": m.get("context_length") or 0,
        })
    out.sort(key=lambda x: (-x["context_length"], x["id"]))
    return out


def _is_zero(price: str) -> bool:
    try:
        return float(price) == 0.0
    except (TypeError, ValueError):
        return False


def _gemini_version_key(model_id: str) -> float:
    """Извлечь версию (3.1, 2.5, 2.0, 1.5) для сортировки. Latest/preview → high."""
    if "latest" in model_id:
        return 99.0
    import re
    m = re.search(r"gemini-(\d+\.\d+|\d+)", model_id)
    if not m:
        return 0.0
    try:
        return float(m.group(1))
    except ValueError:
        return 0.0
