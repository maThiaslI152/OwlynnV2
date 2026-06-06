"""
User Profile Manager
--------------------
Stores and retrieves user preferences from data/user_profile.json.
"""

import json
from pathlib import Path

_PROFILE_PATH = Path(__file__).parent.parent.parent / "data" / "user_profile.json"

_DEFAULTS = {
    # ── User identity & preferences ─────────────────────────────────────
    "name": "User",
    "preferred_language": "en",
    "education_level": "university",
    "domains_of_interest": [],
    "response_style": "detailed",
    "system_prompt": "",
    "custom_instructions": "",
    # ── Memory ──────────────────────────────────────────────────────────
    "short_term_enabled": True,
    "long_term_enabled": True,
    # ── Display ─────────────────────────────────────────────────────────
    "streaming_enabled": True,
    "show_thinking": False,
    "show_tool_execution": True,
    # ── Execution ───────────────────────────────────────────────────────
    "execution_policy": "auto_approve",
    # ── Audit logging ───────────────────────────────────────────────────
    "audit_log_enabled": True,
    "audit_log_levels": {},
    "audit_log_dir": "",
    # ── Config overrides are NOT in _DEFAULTS — see note below ───────────
    # The following fields exist ONLY when the user explicitly sets them
    # in data/user_profile.json. If absent, code reads defaults from
    # src/config/defaults.yaml via the centralized config loader.
    #
    # Overridable fields (set in profile JSON only to override YAML):
    #   llm_base_url, llm_model_name, small_llm_base_url, small_llm_model_name,
    #   large_llm_base_url, large_llm_model_name, cloud_llm_base_url,
    #   cloud_llm_model_name, deepseek_api_key, redis_url,
    #   lm_studio_fold_system, temperature, top_p, max_tokens, top_k,
    #   router_hitl_enabled, route_confidence_threshold,
    #   skill_clarification_threshold, router_clarification_threshold,
    #   scope_clarification_enabled, plan_review_enabled,
    #   cloud_escalation_enabled, cloud_anonymization_enabled,
    #   custom_sensitive_terms, cloud_brief_enabled, cloud_brief_max_chars,
}

VALID_FIELDS = {
    # User identity & preferences
    "name": str,
    "preferred_language": str,
    "education_level": str,
    "domains_of_interest": list,
    "response_style": str,
    "system_prompt": str,
    "custom_instructions": str,
    # Memory
    "short_term_enabled": bool,
    "long_term_enabled": bool,
    # Display
    "streaming_enabled": bool,
    "show_thinking": bool,
    "show_tool_execution": bool,
    # Execution
    "execution_policy": str,
    # Audit logging
    "audit_log_enabled": bool,
    "audit_log_levels": dict,
    "audit_log_dir": str,
    # ── Config overrides (allow None = "use default") ──────────────────
    "llm_base_url": str,
    "llm_model_name": str,
    "small_llm_base_url": str,
    "small_llm_model_name": str,
    "large_llm_base_url": str,
    "large_llm_model_name": str,
    "cloud_llm_base_url": str,
    "cloud_llm_model_name": str,
    "deepseek_api_key": str,
    "redis_url": str,
    "lm_studio_fold_system": (bool, type(None)),
    "temperature": (int, float, type(None)),
    "top_p": (int, float, type(None)),
    "max_tokens": (int, type(None)),
    "top_k": (int, type(None)),
    "router_hitl_enabled": (bool, type(None)),
    "route_confidence_threshold": (int, float, type(None)),
    "skill_clarification_threshold": (int, float, type(None)),
    "router_clarification_threshold": (int, float, type(None)),
    "scope_clarification_enabled": (bool, type(None)),
    "plan_review_enabled": (bool, type(None)),
    "cloud_escalation_enabled": (bool, type(None)),
    "cloud_anonymization_enabled": (bool, type(None)),
    "custom_sensitive_terms": list,
    "cloud_brief_enabled": (bool, type(None)),
    "cloud_brief_max_chars": (int, type(None)),
}


def get_profile() -> dict:
    """Load and return the current user profile."""
    try:
        with open(_PROFILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Merge with defaults for any missing keys
        return {**_DEFAULTS, **data}
    except (FileNotFoundError, json.JSONDecodeError):
        _save_profile(_DEFAULTS)
        return _DEFAULTS.copy()


def update_profile(field: str, value) -> dict:
    """Update a single field in the user profile and return the updated profile."""
    if field not in VALID_FIELDS:
        raise ValueError(
            f"Unknown profile field '{field}'. Valid fields: {list(VALID_FIELDS.keys())}"
        )

    profile = get_profile()

    # Coerce value type
    expected_type = VALID_FIELDS[field]
    if expected_type is list and isinstance(value, str):
        value = [v.strip() for v in value.split(",")]

    profile[field] = value
    _save_profile(profile)
    return profile


def _save_profile(profile: dict):
    _PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)


def profile_to_context(profile: dict) -> str:
    """Format the profile as a system prompt context block."""
    lang_map = {"en": "English", "th": "Thai", "ja": "Japanese", "zh": "Chinese"}
    lang = lang_map.get(
        profile.get("preferred_language", "en"),
        profile.get("preferred_language", "English"),
    )
    domains = ", ".join(profile.get("domains_of_interest", [])) or "general topics"

    return (
        f"USER PROFILE:\n"
        f"- Name: {profile.get('name', 'User')}\n"
        f"- Preferred response language: {lang}\n"
        f"- Education level: {profile.get('education_level', 'university')}\n"
        f"- Domains of interest: {domains}\n"
        f"- Response style: {profile.get('response_style', 'detailed')}\n"
        f"Always address the user by their name and adapt your language and depth accordingly."
    )
