"""LLM administration: test connection, regenerate-all, list models."""
import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.ai_deps import require_ai_enabled
from app.database import get_db
from app.jobs.regenerate_summaries import regenerate_outdated_summaries_blocking
from app.services.llm.base import ConfigurationError, get_llm_provider
from app.services.llm.prompt import DEFAULT_SYSTEM_ROLE, FORMAT_SPEC
from app.models.app_setting import AppSetting


router = APIRouter()


@router.post("/test", dependencies=[Depends(require_ai_enabled)])
async def test_connection(db: Session = Depends(get_db)):
    """Проверка соединения с настроенным LLM-провайдером."""
    try:
        provider = get_llm_provider(db)
    except ConfigurationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    ok = await provider.healthcheck()
    error = getattr(provider, "last_error", None) if not ok else None
    return {"ok": ok, "provider": provider.name, "model": provider.model, "error": error}


@router.post("/regenerate-all", dependencies=[Depends(require_ai_enabled)])
async def regenerate_all(background: BackgroundTasks):
    """Запускает в background регенерацию всех устаревших AI-саммари."""
    background.add_task(regenerate_outdated_summaries_blocking)
    return {"started": True}


@router.get("/prompt-default")
async def get_prompt_default():
    """Дефолтный текст системного промпта (роль/тон) + read-only описание формата.

    `system_role` — редактируется пользователем через AppSetting
    `llm_project_summary_system_prompt`. `format_spec` — хардкод JSON-схемы,
    нельзя менять без правки backend-схемы.
    """
    return {"system_role": DEFAULT_SYSTEM_ROLE, "format_spec": FORMAT_SPEC}


GEO_BLOCK_MSG = (
    "Google не обслуживает запросы из текущего региона. "
    "Нужен доступ через другую страну либо переключитесь на OpenRouter в Настройках → AI."
)


# Префиксы моделей, не подходящих для текстового AI-саммари
_GEMINI_EXCLUDE_KEYWORDS = (
    "tts", "image", "robotics", "computer-use", "embedding",
    "lyria", "nano-banana", "gemma", "deep-research",
)


@router.get("/gemini/models", dependencies=[Depends(require_ai_enabled)])
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
        if "location is not supported" in (e.response.text or ""):
            raise HTTPException(status_code=503, detail=GEO_BLOCK_MSG)
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


@router.get("/openrouter/models", dependencies=[Depends(require_ai_enabled)])
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
        # Только текстовые: у аудио-моделей (lyria и пр.) в выходах не один text.
        arch = m.get("architecture") or {}
        if list(arch.get("output_modalities") or ["text"]) != ["text"]:
            continue
        out.append({
            "id": model_id,
            "label": m.get("name", model_id),
            "context_length": m.get("context_length") or 0,
        })
    out.sort(key=lambda x: (-x["context_length"], x["id"]))
    return out


@router.get("/deepseek/models", dependencies=[Depends(require_ai_enabled)])
async def list_deepseek_models(db: Session = Depends(get_db)):
    """Live-список моделей DeepSeek через `/v1/models`.

    DeepSeek возвращает короткий список (deepseek-chat, deepseek-reasoner).
    Сортировка: имя по алфавиту.
    """
    row = db.query(AppSetting).filter(AppSetting.key == "llm_deepseek_api_key").first()
    if not row or not row.value:
        raise HTTPException(status_code=400, detail="DeepSeek API key not configured")

    url = "https://api.deepseek.com/v1/models"
    headers = {"Authorization": f"Bearer {row.value}"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=503, detail=f"DeepSeek API ответил {e.response.status_code}")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"DeepSeek API недоступен: {e}")

    out: list[dict] = []
    for m in data.get("data", []):
        model_id = m.get("id", "")
        if not model_id:
            continue
        out.append({"id": model_id, "label": model_id})
    out.sort(key=lambda x: x["id"])
    return out


@router.get("/omniroute/models", dependencies=[Depends(require_ai_enabled)])
async def list_omniroute_models(db: Session = Depends(get_db)):
    """Live-список моделей внутреннего шлюза OmniRoute через `/models`.

    Ключ опционален — свежая установка шлюза отвечает без авторизации.
    Псевдо-модели авто-роутинга (`auto`, `auto/coding`, `auto/cheap`) шлюз в
    списке не отдаёт, поэтому добавляем их вручную первыми.
    """
    from app.services.llm.omniroute import DEFAULT_BASE_URL

    def _setting(key: str) -> str:
        row = db.query(AppSetting).filter(AppSetting.key == key).first()
        return (row.value if row else "") or ""

    base_url = (_setting("llm_omniroute_base_url") or DEFAULT_BASE_URL).rstrip("/")
    headers = {}
    api_key = _setting("llm_omniroute_api_key")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(f"{base_url}/models", headers=headers)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=503, detail=f"OmniRoute ответил {e.response.status_code}")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"OmniRoute недоступен: {e}")

    auto = [
        {"id": "auto", "label": "auto — балансировка"},
        {"id": "auto/coding", "label": "auto/coding — качество"},
        {"id": "auto/cheap", "label": "auto/cheap — дешевле"},
    ]
    auto_ids = {m["id"] for m in auto}
    out: list[dict] = []
    for m in data.get("data", []):
        model_id = m.get("id", "")
        if not model_id or model_id in auto_ids:
            continue
        out.append({"id": model_id, "label": model_id})
    out.sort(key=lambda x: x["id"])
    return auto + out


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
