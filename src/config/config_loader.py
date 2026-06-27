"""
Centralized Configuration Loader.

Priority chain (lowest → highest):
  1. defaults.yaml           — single source of truth for all defaults
  2. Environment variables    — override via standard env var names
  3. User profile JSON        — user-editable runtime overrides

Usage::

    from src.config.config_loader import config

    model_name = config.get("models.small.model_name")
    # or via the typed accessor
    from src.config.config_loader import get_model_config
    cfg = get_model_config("small")
    print(cfg["model_name"])

Module-level singletons are available for backward compatibility with the
existing ``settings.py`` module-level constants.

Note on Architecture:
The agent runs a unified local small tier for routing, vision proxying, and extraction, backed by DeepSeek V4 for complex reasoning.
"""

from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).parent
_DEFAULTS_PATH = _CONFIG_DIR / "defaults.yaml"

from src.config.env_files import load_project_env_files

load_project_env_files()

# ── Environment variable → config dot-path mapping ────────────────────────────
# Keys: env var name.  Values: dot-path into the defaults.yaml structure.
_ENV_OVERRIDE_MAP: dict[str, str] = {
    # Server
    "HOST": "server.host",
    "PORT": "server.port",
    # External services
    "QDRANT_HOST": "external_services.qdrant.host",
    "QDRANT_PORT": "external_services.qdrant.port",
    "REDIS_URL": "external_services.redis.url",
    "SEARXNG_URL": "external_services.searxng.url",
    "STIRLING_PDF_URL": "external_services.stirling_pdf.url",
    "STIRLING_PDF_API_KEY": "external_services.stirling_pdf.api_key",
    "STIRLING_PDF_ENABLED": "external_services.stirling_pdf.enabled",
    "STIRLING_PDF_TIMEOUT_SECONDS": "external_services.stirling_pdf.timeout_seconds",
    "STIRLING_PDF_OCR_LANGUAGES": "external_services.stirling_pdf.ocr_languages",
    "STIRLING_PDF_MIN_TEXT_CHARS": "external_services.stirling_pdf.min_text_chars",
    # Small model
    "SMALL_LLM_BASE_URL": "models.small.base_url",
    "SMALL_LLM_MODEL_NAME": "models.small.model_name",
    # Cloud model
    "CLOUD_LLM_BASE_URL": "models.cloud.base_url",
    "CLOUD_LLM_MODEL_NAME": "models.cloud.model_name",
    # Voice
    "VOICE_WAKE_WORD": "server.voice.wake_word",
    "VOICE_AUTO_TTS": "server.voice.auto_tts",
    # Web RAG
    "WEB_RAG_ENABLED": "web_rag.enabled",
    "WEB_RAG_EMBED_MODEL": "web_rag.embed_model",
    "WEB_RAG_TOP_K": "web_rag.top_k",
    "WEB_RAG_CHUNK_CHARS": "web_rag.chunk_chars",
    "WEB_RAG_CHUNK_OVERLAP": "web_rag.chunk_overlap",
    "WEB_RAG_MIN_CHARS_FOR_RANK": "web_rag.min_chars_for_rank",
    "WEB_SEARCH_RERANK_TOP_N": "web_rag.rerank_top_n",
    # Web search
    "WEB_SEARCH_TIMEOUT_SECONDS": "web_search.timeout_seconds",
    "WEB_SEARCH_ENABLE_CURL_CFFI": "web_search.enable_curl_cffi",
    "WEB_SEARCH_ENABLE_BROWSER_FALLBACK": "web_search.enable_browser_fallback",
    # Screen assist
    "KALI_SSH_HOST": "screen_assist.kali.host",
    "KALI_SSH_USER": "screen_assist.kali.user",
    "KALI_SSH_PORT": "screen_assist.kali.port",
    "SCREEN_ASSIST_TMUX_SESSION": "screen_assist.tmux_session",
}

# ── User profile key → config dot-path mapping ───────────────────────────────
# Maps user_profile.json fields to the centralized config structure.
_PROFILE_OVERRIDE_MAP: dict[str, str] = {
    # LLM base URLs
    "small_llm_base_url": "models.small.base_url",
    # Cloud
    "cloud_llm_base_url": "models.cloud.base_url",
    "cloud_llm_model_name": "models.cloud.model_name",
    # Redis
    "redis_url": "external_services.redis.url",
    # Routing thresholds
    "route_confidence_threshold": "routing.confidence_threshold",
    "skill_clarification_threshold": "routing.skill_clarification_threshold",
    "router_clarification_threshold": "routing.router_clarification_threshold",
    "router_hitl_enabled": "routing.hitl_enabled",
    "scope_clarification_enabled": "routing.scope_clarification_enabled",
    "plan_review_enabled": "routing.plan_review_enabled",
    # Cloud config
    "cloud_escalation_enabled": "cloud.escalation_enabled",
    "cloud_anonymization_enabled": "cloud.anonymization_enabled",
    "cloud_brief_enabled": "cloud.escalation_enabled",
    "cloud_brief_max_chars": "cloud.budget.brief_max_chars",
}


# ═══════════════════════════════════════════════════════════════════════════════
# Core loader
# ═══════════════════════════════════════════════════════════════════════════════


class ConfigLoader:
    """Layered configuration manager.

    Loads defaults.yaml once, then applies env var and user profile overrides
    on each access so that profile changes are reflected at runtime.
    """

    _defaults: dict[str, Any] | None = None
    _env_overrides_applied: bool = False

    @classmethod
    def _load_defaults(cls) -> dict[str, Any]:
        """Load and cache the raw defaults.yaml content."""
        if cls._defaults is not None:
            return cls._defaults

        if not _DEFAULTS_PATH.exists():
            logger.warning(
                "defaults.yaml not found at %s, using empty config", _DEFAULTS_PATH
            )
            cls._defaults = {}
            return cls._defaults

        try:
            import yaml
        except ImportError:
            logger.warning("PyYAML not installed — using empty config")
            cls._defaults = {}
            return cls._defaults

        with open(_DEFAULTS_PATH, "r", encoding="utf-8") as f:
            cls._defaults = yaml.safe_load(f) or {}

        logger.debug("Loaded defaults.yaml (%d top-level keys)", len(cls._defaults))
        return cls._defaults

    @classmethod
    def _resolve_dotpath(cls, data: dict, path: str) -> Any:
        """Resolve a dotted path into a nested dict, returning the value."""
        parts = path.split(".")
        current: Any = data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
            if current is None:
                return None
        return current

    @classmethod
    def _set_dotpath(cls, data: dict, path: str, value: Any) -> None:
        """Set a value at a dotted path, creating intermediate dicts as needed."""
        parts = path.split(".")
        current = data
        for part in parts[:-1]:
            if part not in current or not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value

    @classmethod
    def _apply_env_overrides(cls, data: dict) -> dict:
        """Apply environment variable overrides to the config dict."""
        import copy

        result = copy.deepcopy(data)

        for env_var, dotpath in _ENV_OVERRIDE_MAP.items():
            val = os.getenv(env_var)
            if val is not None and val != "":
                # Coerce type based on the existing default
                existing = cls._resolve_dotpath(result, dotpath)
                if isinstance(existing, bool):
                    coerced = val.strip().lower() in {"1", "true", "yes", "on"}
                elif isinstance(existing, int):
                    try:
                        coerced = int(val)
                    except ValueError:
                        coerced = val
                elif isinstance(existing, float):
                    try:
                        coerced = float(val)
                    except ValueError:
                        coerced = val
                else:
                    coerced = val

                cls._set_dotpath(result, dotpath, coerced)
                logger.debug("env override: %s → %s = %s", env_var, dotpath, coerced)

        # M4 optimization — apply standard overrides if not M4
        m4_enabled = (
            os.getenv("MACHINE_TYPE") == "M4_MAC"
            or os.getenv("OPTIMIZE_FOR_M4", "").lower() == "true"
        )
        if not m4_enabled:
            std = cls._resolve_dotpath(result, "models.standard")
            if std:
                for tier, overrides in std.items():
                    for key, val in overrides.items():
                        dotpath = f"models.{tier}.{key}"
                        cls._set_dotpath(result, dotpath, val)
                        logger.debug(
                            "standard override (non-M4): %s = %s", dotpath, val
                        )

        return result

    @classmethod
    def _apply_profile_overrides(cls, data: dict) -> dict:
        """Apply user profile overrides (from data/user_profile.json)."""
        import copy

        result = copy.deepcopy(data)

        try:
            from src.memory.user_profile import get_profile

            profile = get_profile()
        except Exception as e:
            logger.warning("Error suppressed: %s", e)
            return result

        for profile_key, dotpath in _PROFILE_OVERRIDE_MAP.items():
            val = profile.get(profile_key)
            if val is not None and val != "" and val != [] and val != {}:
                # Special handling for inference params
                if profile_key == "temperature":
                    cls._set_dotpath(result, "models.small.temperature", val)
                    cls._set_dotpath(result, "models.cloud.temperature", val)
                    continue
                if profile_key == "max_tokens":
                    cls._set_dotpath(result, "models.cloud.max_tokens", val)
                    cls._set_dotpath(result, "models.cloud.max_output_tokens", val)
                    continue

                cls._set_dotpath(result, dotpath, val)

        return result

    @classmethod
    def get_config(cls) -> dict[str, Any]:
        """Return the fully-resolved configuration dict.

        Re-applies profile overrides on every call so that runtime profile
        changes (e.g. via Settings UI) are reflected immediately.
        """
        data = cls._load_defaults()
        data = cls._apply_env_overrides(data)
        data = cls._apply_profile_overrides(data)
        return data

    @classmethod
    def get(cls, dotpath: str, default: Any = None) -> Any:
        """Get a single config value by dot-path.

        Example: ``config.get("models.small.model_name")``
        """
        data = cls.get_config()
        val = cls._resolve_dotpath(data, dotpath)
        return val if val is not None else default

    @classmethod
    def reload(cls) -> None:
        """Force-reload defaults.yaml (useful after file changes)."""
        cls._defaults = None
        cls._env_overrides_applied = False

    # ── Model name accessors — single source of truth for model selection ──

    @classmethod
    def get_small_model_name(cls) -> str:
        """Return the configured local model name (router, fallback, vision, extraction)."""
        return cls.get(
            "models.small.model_name", "qwen3-vl-4b-instruct-c_abliterated-v2-mlx"
        )

    @classmethod
    def get_cloud_model_name(cls) -> str:
        """Return the configured cloud model name (DeepSeek flash tier)."""
        return cls.get("models.cloud.model_name", "deepseek-v4-flash")

    @classmethod
    def get_embedding_model_name(cls) -> str:
        """Return the configured embedding model name."""
        return cls.get(
            "models.embedding.model_name",
            "text-embedding-nomic-embed-text-v1.5-embedding",
        )


# ── Module-level singleton for convenience ───────────────────────────────────

config = ConfigLoader()


# ═══════════════════════════════════════════════════════════════════════════════
# Typed accessor functions — backward compatible with existing patterns
# ═══════════════════════════════════════════════════════════════════════════════


def get_model_config(tier: str, variant: str = "default") -> dict[str, Any]:
    """Return the full model config dict for a given tier.

    Args:
        tier: ``"small"``, ``"cloud"``, or ``"embedding"``

    Returns a dict with keys: model_name, base_url, temperature, max_tokens,
    max_output_tokens, timeout, context_window, extra_body, etc.
    """
    return config.get(f"models.{tier}") or {}


def get_m4_optimization() -> dict[str, Any]:
    """Return the M4 optimization dict (backward compat with M4_MAC_OPTIMIZATION)."""
    cfg = config.get_config()
    return {
        "small_model": {
            "max_tokens": cfg.get("models", {}).get("small", {}).get("max_tokens", 512),
            "context_length": cfg.get("models", {})
            .get("small", {})
            .get("context_window", 4096),
            "temperature": cfg.get("models", {})
            .get("small", {})
            .get("temperature", 0.1),
            "timeout": cfg.get("models", {}).get("small", {}).get("timeout", 10),
        },
        "extraction_model": {
            "model_name": cfg.get("models", {})
            .get("small", {})
            .get("model_name", "qwen3-vl-4b-instruct-c_abliterated-v2-mlx"),
            "max_tokens": cfg.get("models", {})
            .get("small", {})
            .get("max_tokens", 1024),
            "temperature": cfg.get("models", {})
            .get("small", {})
            .get("temperature", 0.1),
            "timeout": cfg.get("models", {}).get("small", {}).get("timeout", 120),
        },
        "memory": {
            "max_facts": cfg.get("memory", {}).get("max_facts", 200),
            "search_window": cfg.get("memory", {}).get("search_window_m4", 100),
            "cache_ttl": cfg.get("memory", {}).get("cache", {}).get("ttl", 300),
            "cache_cleanup": cfg.get("memory", {})
            .get("cache", {})
            .get("cleanup_interval", 600),
        },
        "checkpoint": {
            "memory_cleanup_interval": cfg.get("memory", {}).get(
                "thread_cleanup_interval", 3600
            ),
        },
        "routing": {
            "keyword_bypass": cfg.get("routing", {}).get("keyword_bypass", True),
            "simple_prompt": cfg.get("routing", {}).get("simple_prompt", True),
        },
        "threading": {
            "max_workers": cfg.get("threading", {}).get("max_workers", 2),
            "queue_size": cfg.get("threading", {}).get("queue_size", 10),
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Config validation — runs at startup to detect mismatches
# ═══════════════════════════════════════════════════════════════════════════════

_REQUIRED_PATHS: list[str] = [
    # Server
    "server.host",
    "server.port",
    # External services
    "external_services.qdrant.host",
    "external_services.qdrant.port",
    "external_services.redis.url",
    "external_services.lm_studio.base_url",
    "external_services.lm_studio.management_url",
    # Models — small
    "models.small.base_url",
    "models.small.model_name",
    "models.small.temperature",
    "models.small.max_tokens",
    "models.small.context_window",
    "models.small.timeout",
    # Models — cloud
    "models.cloud.base_url",
    "models.cloud.model_name",
    "models.cloud.timeout",
    "models.cloud.context_window",
    # Models — embedding
    "models.embedding.base_url",
    "models.embedding.model_name",
    "models.embedding.timeout",
    # Startup
    "startup.preload",
    "startup.warmup",
    # Routing
    "routing.confidence_threshold",
    "routing.swap_threshold",
    "routing.max_input_chars",
    "routing.hitl_enabled",
    "routing.budget_tiers",
    "routing.input_reserves",
    "routing.budget_max",
    # Memory
    "memory.max_facts",
    "memory.search_window",
    "memory.cache.ttl",
    # Web
    "web_search.timeout_seconds",
    "web_search.timeouts.aggregate",
    "web_rag.enabled",
    "web_rag.top_k",
    "web_rag.chunk_chars",
    # Summarization
    "summarization.threshold_ratio",
    "summarization.keep_recent_turns",
    # Complex
    "complex.min_output_tokens",
    "complex.max_cutoff_retries",
    "complex.default_token_budget",
    # Cloud infra
    "cloud.circuit_breaker.failure_threshold",
    "cloud.circuit_breaker.cooldown_seconds",
    # Tool output
    "tool_output.max_tool_output_chars",
    "tool_output.max_read_chars",
    # Threading
    "threading.max_workers",
    # Router LLM
    "router_llm.temperature",
    "router_llm.max_tokens",
    # Chat title
    "chat_title.temperature",
    "chat_title.max_tokens",
]


def validate_config() -> dict[str, list[str]]:
    """Validate that all required config paths resolve. Returns {missing, warnings}."""
    missing: list[str] = []
    warnings: list[str] = []

    cfg = config.get_config()
    if not cfg:
        warnings.append("defaults.yaml is empty or failed to load")
        return {"missing": _REQUIRED_PATHS, "warnings": warnings}

    for path in _REQUIRED_PATHS:
        val = config.get(path)
        if val is None or val == "":
            missing.append(path)

    # Check top-level keys exist
    expected_sections = [
        "server",
        "external_services",
        "models",
        "routing",
        "memory",
        "web_search",
        "web_rag",
        "summarization",
        "complex",
        "cloud",
        "tool_output",
        "file_indexing",
        "pdf_rendering",
        "audit",
        "trace",
        "threading",
        "secret_store",
        "file_decode",
        "chat_title",
        "router_llm",
    ]
    cfg_keys = set(cfg.keys())
    for section in expected_sections:
        if section not in cfg_keys:
            warnings.append(f"Missing top-level section: {section}")

    return {"missing": missing, "warnings": warnings}
