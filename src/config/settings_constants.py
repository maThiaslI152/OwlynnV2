from src.config.config_loader import config

_LLM_SENSITIVE_FIELDS = {
    "cloud_llm_base_url",
    "cloud_llm_model_name",
    "deepseek_api_key",
    "cloud_request_timeout",
    "llm_base_url",
    "llm_model_name",
    "large_llm_base_url",
    "large_llm_model_name",
    "small_llm_base_url",
    "small_llm_model_name",
}

_ADVANCED_SETTINGS_DEFAULTS = {
    "temperature": 0.7,
    "top_p": 0.9,
    "max_tokens": int(config.get("models.standard.small.max_tokens") or 1024),
    "top_k": 40,
    "streaming_enabled": True,
    "show_thinking": False,
    "show_tool_execution": True,
    "cloud_escalation_enabled": True,
    "cloud_anonymization_enabled": True,
    "router_hitl_enabled": True,
    "router_clarification_threshold": 0.6,
    "execution_policy": "auto_approve",
    "safe_mode": "normal",
    "custom_sensitive_terms": [],
    "redis_url": "redis://localhost:6379",
    "lm_studio_fold_system": True,
}

_UNIFIED_SETTINGS_CLOUD_BUDGET_DEFAULTS = {
    "cloud_daily_token_limit": config.get("cloud.budget.daily_token_limit", 500_000),
    "cloud_budget_warning_thresholds": config.get(
        "cloud.budget.warning_thresholds", [0.5, 0.8, 0.95]
    ),
}
