from fastapi import APIRouter, HTTPException

from src.config.settings_constants import (
    _ADVANCED_SETTINGS_DEFAULTS,
    _UNIFIED_SETTINGS_CLOUD_BUDGET_DEFAULTS,
)

router = APIRouter()
import logging

logger = logging.getLogger(__name__)
from src.config.config_loader import config
from src.memory.persona import get_persona, update_persona_field
from src.memory.user_profile import VALID_FIELDS, get_profile, update_profile


@router.get("/api/system-settings")
async def api_get_system_settings():
    """Get system prompts and instructions."""
    try:
        profile = get_profile()
        persona = get_persona()
        return {
            "system_prompt": profile.get("system_prompt", ""),
            "custom_instructions": profile.get("custom_instructions", ""),
            "name": persona.get("name", "Owlynn"),
            "tone": persona.get("tone", "friendly"),
        }
    except Exception as e:
        logger.error("Error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/system-settings")
async def api_update_system_settings(body: dict):
    """Update system prompts and instructions."""
    try:
        update_profile("system_prompt", body.get("system_prompt", ""))
        update_profile("custom_instructions", body.get("custom_instructions", ""))
        if body.get("name"):
            update_persona_field("name", body["name"])
        if body.get("tone"):
            update_persona_field("tone", body["tone"])
        return {"status": "ok", "message": "System settings saved"}
    except Exception as e:
        logger.error("Error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/memory-settings")
async def api_get_memory_settings():
    """Get memory settings."""
    try:
        profile = get_profile()
        return {
            "short_term_enabled": profile.get("short_term_enabled", True),
            "long_term_enabled": profile.get("long_term_enabled", True),
        }
    except Exception as e:
        logger.error("Error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/memory-settings")
async def api_update_memory_settings(body: dict):
    """Update memory settings."""
    try:
        if "short_term_enabled" in body:
            update_profile("short_term_enabled", body["short_term_enabled"])
        if "long_term_enabled" in body:
            update_profile("long_term_enabled", body["long_term_enabled"])
        return {"status": "ok", "message": "Memory settings saved"}
    except Exception as e:
        logger.error("Error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/advanced-settings")
async def api_get_advanced_settings():
    """Get inference and behavior settings."""
    try:
        profile = get_profile()
        return {
            field: profile.get(field, default)
            for field, default in _ADVANCED_SETTINGS_DEFAULTS.items()
        }
    except Exception as e:
        logger.error("Error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/unified-settings")
async def api_get_unified_settings():
    """Get merged profile and advanced settings in one payload."""
    try:
        from src.config.secret_store import (
            resolve_deepseek_api_key,
            resolve_openrouter_api_key,
        )

        profile = get_profile()
        unified = dict(profile)
        unified.update(
            {
                field: profile.get(field, default)
                for field, default in _ADVANCED_SETTINGS_DEFAULTS.items()
            }
        )
        # These budget fields may not exist in old profiles; provide stable defaults.
        unified.update(
            {
                field: profile.get(field, default)
                for field, default in _UNIFIED_SETTINGS_CLOUD_BUDGET_DEFAULTS.items()
            }
        )
        _CLOUD_UI_DEFAULTS = {
            "cloud_model_tier": "flash",
            "cloud_thinking_mode": "auto",
            "cloud_reasoning_effort": "high",
        }
        unified.update(
            {
                field: profile.get(field, default)
                for field, default in _CLOUD_UI_DEFAULTS.items()
                if profile.get(field) is None
            }
        )

        # Ensure all LLM override fields are present in the response
        llm_fields = {
            "main_llm_base_url": "models.main.base_url",
            "main_llm_model_name": "models.main.model_name",
            "llm_base_url": "models.main.base_url",
            "small_llm_base_url": "models.main.base_url",
            "large_llm_base_url": "models.main.base_url",
            "llm_model_name": "models.main.model_name",
            "small_llm_model_name": "models.main.model_name",
            "large_llm_model_name": "models.main.model_name",
            "pentest_llm_model_name": "models.pentest.model_name",
            "vision_llm_model_name": "models.vision.model_name",
            "embedding_llm_model_name": "models.embedding.model_name",
            "cloud_llm_base_url": "models.cloud.base_url",
            "cloud_llm_model_name": "models.cloud.model_name",
        }
        for field, dotpath in llm_fields.items():
            if field not in unified or unified[field] is None:
                unified[field] = config.get(dotpath)

        # Never expose raw API keys to the frontend.
        # Check Keychain first, then env var, then (deprecated) profile.
        deepseek_key = resolve_deepseek_api_key()
        unified["deepseek_api_key"] = "••••••••" if deepseek_key else ""
        openrouter_key = resolve_openrouter_api_key()
        unified["openrouter_api_key"] = "••••••••" if openrouter_key else ""
        return unified
    except Exception as e:
        logger.error("Error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/api/unified-settings")
async def api_update_unified_settings(body: dict):
    """Update unified profile and advanced settings in one payload.

    The ``deepseek_api_key`` field is stored in macOS Keychain (not profile).
    Pass ``""`` (empty string) to delete the key.
    """
    try:
        from src.config.secret_store import (
            delete_deepseek_api_key,
            delete_openrouter_api_key,
            store_deepseek_api_key,
            store_openrouter_api_key,
        )

        # Allowed fields: profile VALID_FIELDS + advanced settings defaults + cloud budget
        allowed = (
            set(VALID_FIELDS.keys())
            | set(_ADVANCED_SETTINGS_DEFAULTS.keys())
            | set(_UNIFIED_SETTINGS_CLOUD_BUDGET_DEFAULTS.keys())
        )
        updated = []
        for field, value in body.items():
            if field == "deepseek_api_key":
                key_value = str(value).strip() if value else ""
                if key_value and key_value != "••••••••":
                    store_deepseek_api_key(key_value)
                    updated.append(field)
                elif not key_value:
                    delete_deepseek_api_key()
                    updated.append(field)
            elif field == "openrouter_api_key":
                key_value = str(value).strip() if value else ""
                if key_value and key_value != "••••••••":
                    store_openrouter_api_key(key_value)
                    updated.append(field)
                elif not key_value:
                    delete_openrouter_api_key()
                    updated.append(field)
            elif field in allowed:
                update_profile(field, value)
                updated.append(field)
        if any(
            f in updated
            for f in (
                "cloud_model_tier",
                "cloud_llm_model_name",
                "cloud_thinking_mode",
                "cloud_reasoning_effort",
                "cloud_escalation_enabled",
                "cloud_routing_mode",
                "travel_mode",
                "deepseek_api_key",
                "openrouter_api_key",
                "cloud_provider",
                "openrouter_model",
            )
        ):
            from src.agent.cloud.cloud_circuit_breaker import reset_circuit_breaker
            from src.agent.llm import LLMPool

            LLMPool.clear()
            reset_circuit_breaker()
        return {"status": "ok", "updated": updated}
    except Exception as e:
        logger.error("Error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/advanced-settings")
async def api_update_advanced_settings(body: dict):
    """Update inference and behavior settings."""
    try:
        for field in _ADVANCED_SETTINGS_DEFAULTS:
            if field in body:
                update_profile(field, body[field])
        return {"status": "ok", "message": "Advanced settings saved"}
    except Exception as e:
        logger.error("Error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
