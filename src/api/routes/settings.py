from fastapi import APIRouter
from src.config.settings_constants import (
    _ADVANCED_SETTINGS_DEFAULTS,
    _UNIFIED_SETTINGS_CLOUD_BUDGET_DEFAULTS,
)

router = APIRouter()
from src.memory.user_profile import get_profile, update_profile, VALID_FIELDS
from src.memory.persona import get_persona, update_persona_field
from src.config.config_loader import config


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
        return {"error": str(e)}


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
        return {"status": "error", "message": str(e)}


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
        return {"error": str(e)}


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
        return {"status": "error", "message": str(e)}


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
        return {"error": str(e)}


@router.get("/api/unified-settings")
async def api_get_unified_settings():
    """Get merged profile and advanced settings in one payload."""
    try:
        from src.config.secret_store import resolve_deepseek_api_key

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

        # Ensure all LLM override fields are present in the response
        llm_fields = {
            "llm_base_url": "models.medium.base_url",
            "small_llm_base_url": "models.small.base_url",
            "large_llm_base_url": "models.medium.base_url",
            "llm_model_name": "models.medium.variants.default.model_name",
            "small_llm_model_name": "models.small.model_name",
            "large_llm_model_name": "models.medium.variants.default.model_name",
            "cloud_llm_base_url": "models.cloud.base_url",
            "cloud_llm_model_name": "models.cloud.model_name",
        }
        for field, dotpath in llm_fields.items():
            if field not in unified or unified[field] is None:
                unified[field] = config.get(dotpath)

        if "medium_models" not in unified or not unified["medium_models"]:
            variants_cfg = config.get("models.medium.variants") or {}
            unified["medium_models"] = {
                variant: v.get("model_name", "") for variant, v in variants_cfg.items()
            }

        # Never expose raw API keys to the frontend.
        # Check Keychain first, then env var, then (deprecated) profile.
        deepseek_key = resolve_deepseek_api_key()
        unified["deepseek_api_key"] = "••••••••" if deepseek_key else ""
        return unified
    except Exception as e:
        return {"error": str(e)}


@router.put("/api/unified-settings")
async def api_update_unified_settings(body: dict):
    """Update unified profile and advanced settings in one payload.

    The ``deepseek_api_key`` field is stored in macOS Keychain (not profile).
    Pass ``""`` (empty string) to delete the key.
    """
    try:
        from src.config.secret_store import (
            store_deepseek_api_key,
            delete_deepseek_api_key,
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
                # Secure storage path — Keychain, not profile
                key_value = str(value).strip() if value else ""
                if key_value and key_value != "••••••••":
                    store_deepseek_api_key(key_value)
                    updated.append(field)
                elif not key_value:
                    delete_deepseek_api_key()
                    updated.append(field)
                # If sent as "••••••••", ignore — it's the masked placeholder
            elif field in allowed:
                update_profile(field, value)
                updated.append(field)
        return {"status": "ok", "updated": updated}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/api/advanced-settings")
async def api_update_advanced_settings(body: dict):
    """Update inference and behavior settings."""
    try:
        for field in _ADVANCED_SETTINGS_DEFAULTS:
            if field in body:
                update_profile(field, body[field])
        return {"status": "ok", "message": "Advanced settings saved"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
