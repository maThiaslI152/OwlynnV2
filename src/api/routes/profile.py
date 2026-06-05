from fastapi import APIRouter
from src.config.settings_constants import _LLM_SENSITIVE_FIELDS

router = APIRouter()
from src.agent.llm import LLMPool
import logging

logger = logging.getLogger(__name__)

from src.memory.user_profile import get_profile, update_profile
from src.memory.persona import get_persona, update_persona_field


@router.get("/api/profile")
async def api_get_profile():
    return get_profile()


@router.post("/api/profile")
async def api_update_profile(body: dict):
    updated_fields: list[str] = []
    update_errors: dict[str, str] = {}
    for field, value in body.items():
        try:
            update_profile(field, value)
            updated_fields.append(field)
        except Exception as exc:
            logger.warning("Error suppressed: %s", exc)
            update_errors[field] = str(exc)
    needs_llm_clear = any(f in _LLM_SENSITIVE_FIELDS for f in updated_fields)
    if needs_llm_clear:
        LLMPool.clear()
    profile = get_profile()
    if update_errors:
        return {
            "status": "partial_success",
            "profile": profile,
            "updated_fields": updated_fields,
            "errors": update_errors,
        }
    return profile


@router.get("/api/persona")
async def api_get_persona():
    return get_persona()


@router.post("/api/persona")
async def api_update_persona(body: dict):
    for field, value in body.items():
        try:
            update_persona_field(field, value)
        except Exception as e:
            logger.warning("[persona] update failed for field %s: %s", field, e)
    return get_persona()


@router.get("/api/personas")
async def api_list_personas():
    """List all available personas (built-in + custom)."""
    from src.memory.persona_manager import list_personas

    return list_personas()


@router.post("/api/personas")
async def api_create_persona(body: dict):
    """Save a new custom persona definition."""
    from src.memory.persona_manager import save_custom_persona

    success = save_custom_persona(body)
    if success:
        return {"status": "ok", "message": f"Saved custom persona: {body.get('id')}"}
    return {
        "status": "error",
        "message": "Failed to save persona (ensure 'id' is unique and not a built-in)",
    }
