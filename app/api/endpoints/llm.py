"""LLM administration: test connection, regenerate-all, list models."""
import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.jobs.regenerate_summaries import regenerate_outdated_summaries
from app.services.llm.base import ConfigurationError, get_llm_provider
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
