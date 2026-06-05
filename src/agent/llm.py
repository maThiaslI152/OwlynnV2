"""
LLM Client Initialization with Instance Pooling for Mac M4 Optimization.

This module provides helpers to initialize the LangChain ChatOpenAI client
configured to connect to a local LM Studio server, with pooling to avoid
re-initialization overhead on Mac M4.

Three-slot pool: small (always loaded) + medium (swappable) + cloud (DeepSeek API).

All model parameters (names, base URLs, temperatures, max_tokens, timeouts)
are sourced from the centralized config (src/config/defaults.yaml).
"""

import asyncio
import logging
from typing import Optional

from langchain_openai import ChatOpenAI

from src.config.config_loader import config, get_model_config
from src.config.settings import DEEPSEEK_API_KEY, M4_MAC_OPTIMIZATION
from src.memory.user_profile import get_profile

logger = logging.getLogger(__name__)

from src.config.audit_log import audit_info, audit_debug, audit_warn


class CloudUnavailableError(Exception):
    """Raised when no valid DeepSeek API key is configured."""


class LLMPool:
    """Singleton pool for LLM instances to avoid re-initialization overhead."""

    _small_llm: Optional[ChatOpenAI] = None
    _medium_llm: Optional[ChatOpenAI] = None
    _cloud_llm: Optional[ChatOpenAI] = None
    _current_medium_variant: Optional[str] = None
    _swap_manager: Optional["SwapManager"] = None  # noqa: F821 — forward ref
    _lock = asyncio.Lock()

    # Test override injection (bypasses LM Studio in tests)
    _test_overrides: dict[str, "ChatOpenAI"] = {}

    @classmethod
    def set_test_overrides(cls, overrides: dict[str, "ChatOpenAI"]) -> None:
        """Set LLM overrides for testing (avoids connecting to LM Studio)."""
        cls._test_overrides = overrides

    @classmethod
    def clear_test_overrides(cls) -> None:
        cls._test_overrides = {}

    # ── small ────────────────────────────────────────────────────────────

    @classmethod
    async def get_small_llm(cls) -> ChatOpenAI:
        """Get or create cached small LLM instance."""
        if "small" in cls._test_overrides:
            audit_debug("agent.model", "pool_test_override", slot="small")
            return cls._test_overrides["small"]
        if cls._small_llm is None:
            try:
                async with cls._lock:
                    if cls._small_llm is None:
                        model_cfg = get_model_config("small")
                        extra_body = dict(model_cfg.get("extra_body") or {})
                        extra_body["max_output_tokens"] = model_cfg.get("max_output_tokens", 512)
                        cls._small_llm = ChatOpenAI(
                            model=model_cfg.get("model_name", "liquid/lfm2.5-1.2b"),
                            api_key="sk-local-no-key-needed",
                            base_url=model_cfg.get("base_url", "http://127.0.0.1:1234/v1"),
                            temperature=model_cfg.get("temperature", 0.2),
                            max_tokens=model_cfg.get("max_tokens"),
                            extra_body=extra_body,
                            request_timeout=model_cfg.get("request_timeout") or model_cfg.get("timeout", 10),
                        )
                        audit_info("agent.model", "pool_instance_created", slot="small",
                                   model=model_cfg.get("model_name"))
            except Exception:
                model_cfg = get_model_config("small")
                extra_body = dict(model_cfg.get("extra_body") or {})
                extra_body["max_output_tokens"] = model_cfg.get("max_output_tokens", 512)
                audit_info("agent.model", "pool_instance_created", slot="small",
                           model=model_cfg.get("model_name"), source="fallback")
                return ChatOpenAI(
                    model=model_cfg.get("model_name", "liquid/lfm2.5-1.2b"),
                    api_key="sk-local-no-key-needed",
                    base_url=model_cfg.get("base_url", "http://127.0.0.1:1234/v1"),
                    temperature=model_cfg.get("temperature", 0.2),
                    max_tokens=model_cfg.get("max_tokens"),
                    extra_body=extra_body,
                    request_timeout=model_cfg.get("request_timeout") or model_cfg.get("timeout", 10),
                )
        else:
            audit_debug("agent.model", "pool_cache_hit", slot="small")
        return cls._small_llm

    # ── medium (swappable local slot) ────────────────────────────────────

    @classmethod
    async def get_medium_llm(cls, variant: str = "default") -> ChatOpenAI:
        """Get or create cached medium LLM instance, swapping if needed.

        Parameters
        ----------
        variant:
            ``"default"`` | ``"vision"`` | ``"longctx"``

        Returns
        -------
        ChatOpenAI
            A LangChain client pointing at the now-loaded LM Studio model.
        """
        if variant in cls._test_overrides:
            return cls._test_overrides[variant]
        if "medium" in cls._test_overrides:
            return cls._test_overrides["medium"]
        if cls._current_medium_variant == variant and cls._medium_llm is not None:
            audit_debug("agent.model", "pool_cache_hit", slot="medium", variant=variant)
            return cls._medium_llm

        async with cls._lock:
            # Double-check after acquiring lock
            if cls._current_medium_variant == variant and cls._medium_llm is not None:
                audit_debug("agent.model", "pool_cache_hit", slot="medium", variant=variant)
                return cls._medium_llm

            # Lazy-init swap manager
            if cls._swap_manager is None:
                from src.agent.swap_manager import SwapManager
                cls._swap_manager = SwapManager()

            await cls._swap_manager.swap_model(variant)

            model_cfg = get_model_config("medium", variant)

            extra_body = dict(model_cfg.get("extra_body") or {})
            extra_body["max_output_tokens"] = model_cfg.get("max_output_tokens", 4096)

            cls._medium_llm = ChatOpenAI(
                model=model_cfg.get("model_name", "gemma-4-e4b-uncensored-hauhaucs-aggressive"),
                api_key="sk-local-no-key-needed",
                base_url=model_cfg.get("base_url", "http://127.0.0.1:1234/v1"),
                temperature=model_cfg.get("temperature", 0.4),
                max_tokens=model_cfg.get("max_tokens"),
                extra_body=extra_body,
                request_timeout=model_cfg.get("request_timeout") or model_cfg.get("timeout", 120),
            )
            cls._current_medium_variant = variant
            audit_info("agent.model", "pool_instance_created", slot="medium",
                       variant=variant, model=model_cfg.get("model_name"))

        return cls._medium_llm

    # ── cloud (DeepSeek API) ──────────────────────────────────────────

    @classmethod
    async def get_cloud_llm(cls) -> ChatOpenAI:
        """Get or create cached Cloud LLM (DeepSeek API) instance.

        Resolves API key via secret store (Keychain → env var → profile).
        Configures a request timeout to prevent hangs on slow API responses.

        Raises
        ------
        CloudUnavailableError
            If no valid API key is found in any source.
        """
        if "cloud" in cls._test_overrides:
            audit_debug("agent.model", "pool_test_override", slot="cloud")
            return cls._test_overrides["cloud"]
        if cls._cloud_llm is not None:
            audit_debug("agent.model", "pool_cache_hit", slot="cloud")
            return cls._cloud_llm

        async with cls._lock:
            if cls._cloud_llm is not None:
                audit_debug("agent.model", "pool_cache_hit", slot="cloud")
                return cls._cloud_llm

            from src.config.secret_store import resolve_deepseek_api_key
            api_key = resolve_deepseek_api_key()
            if not api_key:
                audit_warn("agent.model", "pool_no_api_key", slot="cloud")
                raise CloudUnavailableError(
                    "No DeepSeek API key configured. Set DEEPSEEK_API_KEY env var, "
                    "store in macOS Keychain via Settings, or set deepseek_api_key "
                    "in user profile."
                )

            model_cfg = get_model_config("cloud")

            # Resolve timeout: config → M4 optimization → default 180s
            timeout = float(
                model_cfg.get("timeout")
                or M4_MAC_OPTIMIZATION.get("medium_model", {}).get("cloud_timeout", 180)
            )

            cls._cloud_llm = ChatOpenAI(
                model=model_cfg.get("model_name", "deepseek-v4"),
                api_key=api_key,
                base_url=model_cfg.get("base_url", "https://api.deepseek.com/v1"),
                streaming=True,
                max_tokens=model_cfg.get("max_tokens"),
                temperature=model_cfg.get("temperature", 0.4),
                request_timeout=timeout,
            )
            audit_info("agent.model", "pool_instance_created", slot="cloud",
                       model=model_cfg.get("model_name"))

        return cls._cloud_llm

    # ── backward-compat alias ────────────────────────────────────────────

    @classmethod
    async def get_large_llm(cls) -> ChatOpenAI:
        """Alias kept for backward compatibility during migration."""
        return await cls.get_medium_llm("default")

    # ── housekeeping ─────────────────────────────────────────────────────

    @classmethod
    def clear(cls):
        """Clear cached instances (call when profile or config updates)."""
        cls._small_llm = None
        cls._medium_llm = None
        cls._cloud_llm = None
        cls._current_medium_variant = None
        cls._test_overrides = {}

    # ── private ──────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_deepseek_api_key() -> str:
        """Env var → profile → empty string.

        Kept for backward compatibility with existing callers.
        Prefer ``resolve_deepseek_api_key()`` from ``src.config.secret_store``
        for new code — it includes Keychain lookup.
        """
        if DEEPSEEK_API_KEY:
            return DEEPSEEK_API_KEY
        profile = get_profile()
        profile_key = (profile.get("deepseek_api_key") or "").strip()
        return profile_key


# ── module-level convenience wrappers (unchanged API) ────────────────────

async def get_small_llm() -> ChatOpenAI:
    """Get small LLM instance (pooled for efficiency)."""
    return await LLMPool.get_small_llm()


async def get_large_llm() -> ChatOpenAI:
    """Get large LLM instance (pooled for efficiency)."""
    return await LLMPool.get_large_llm()


async def get_medium_llm(variant: str = "default") -> ChatOpenAI:
    """Get medium LLM instance (pooled, swaps if needed)."""
    return await LLMPool.get_medium_llm(variant)


async def get_cloud_llm() -> ChatOpenAI:
    """Get cloud LLM instance (DeepSeek API)."""
    return await LLMPool.get_cloud_llm()
