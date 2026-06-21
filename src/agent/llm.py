"""LLM pool — small (router), medium (complex), cloud (DeepSeek).

Model names and endpoints: src/config/defaults.yaml. See docs/architecture/overview.md.
"""

import asyncio
import logging
from typing import Optional, TYPE_CHECKING

from langchain_openai import ChatOpenAI


from src.config.config_loader import get_model_config, config
from src.config.settings import DEEPSEEK_API_KEY, M4_MAC_OPTIMIZATION
from src.memory.user_profile import get_profile

logger = logging.getLogger(__name__)

from src.config.audit_log import audit_info, audit_debug, audit_warn


class CloudUnavailableError(Exception):
    """Raised when no valid DeepSeek API key is configured."""


class LLMPool:
    """Singleton pool for LLM instances to avoid re-initialization overhead."""

    _small_llm: Optional[ChatOpenAI] = None

    _cloud_llm_flash: Optional[ChatOpenAI] = None
    _cloud_llm_pro: Optional[ChatOpenAI] = None

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
                        extra_body["max_output_tokens"] = model_cfg.get(
                            "max_output_tokens", 512
                        )
                        cls._small_llm = ChatOpenAI(
                            model=model_cfg.get(
                                "model_name", "gemma-4-e2b-heretic-uncensored-mlx"
                            ),
                            api_key="sk-local-no-key-needed",
                            base_url=model_cfg.get(
                                "base_url", "http://127.0.0.1:1234/v1"
                            ),
                            temperature=model_cfg.get("temperature", 0.2),
                            max_tokens=model_cfg.get("max_tokens"),
                            extra_body=extra_body,
                            request_timeout=model_cfg.get("request_timeout")
                            or model_cfg.get("timeout", 10),
                            stream_chunk_timeout=None,
                        )
                        audit_info(
                            "agent.model",
                            "pool_instance_created",
                            slot="small",
                            model=model_cfg.get("model_name"),
                        )
            except Exception as e:
                logger.warning("Error suppressed: %s", e)
                model_cfg = get_model_config("small")
                extra_body = dict(model_cfg.get("extra_body") or {})
                extra_body["max_output_tokens"] = model_cfg.get(
                    "max_output_tokens", 512
                )
                audit_info(
                    "agent.model",
                    "pool_instance_created",
                    slot="small",
                    model=model_cfg.get("model_name"),
                    source="fallback",
                )
                return ChatOpenAI(
                    model=model_cfg.get(
                        "model_name", "gemma-4-e2b-heretic-uncensored-mlx"
                    ),
                    api_key="sk-local-no-key-needed",
                    base_url=model_cfg.get("base_url", "http://127.0.0.1:1234/v1"),
                    temperature=model_cfg.get("temperature", 0.2),
                    max_tokens=model_cfg.get("max_tokens"),
                    extra_body=extra_body,
                    request_timeout=model_cfg.get("request_timeout")
                    or model_cfg.get("timeout", 10),
                    stream_chunk_timeout=None,
                )
        else:
            audit_debug("agent.model", "pool_cache_hit", slot="small")
        return cls._small_llm

    # ── extraction (gemma-4-e2b background) ──────────────────────────

    @classmethod
    async def get_extraction_llm(cls, *, foreground: bool = True) -> ChatOpenAI:
        """Get or create cached extraction LLM instance. Maps to small LLM in unified architecture."""
        if "extraction" in cls._test_overrides:
            return cls._test_overrides["extraction"]
        return await cls.get_small_llm()

    # ── cloud (DeepSeek API) ──────────────────────────────────────────

    @classmethod
    def _resolve_cloud_model_name(cls, tier: Optional[str] = None) -> str:
        """Map profile tier (flash|pro) to DeepSeek model id."""
        profile = get_profile()
        tier = (tier or profile.get("cloud_model_tier") or "flash").lower()
        tiers = config.get("models.cloud.tiers") or {}
        if tier == "pro":
            return tiers.get("pro") or "deepseek-v4-pro"
        return (
            tiers.get("flash")
            or profile.get("cloud_llm_model_name")
            or "deepseek-v4-flash"
        )

    @classmethod
    async def _build_cloud_client(cls, model_name: str) -> ChatOpenAI:
        """Create a ChatOpenAI client for DeepSeek V4."""
        from src.config.secret_store import resolve_deepseek_api_key
        from src.config.config_loader import config

        api_key = resolve_deepseek_api_key()
        if not api_key:
            raise CloudUnavailableError(
                "No DeepSeek API key configured. Set DEEPSEEK_API_KEY env var, "
                "store in macOS Keychain via Settings, or set deepseek_api_key "
                "in user profile."
            )
        model_cfg = get_model_config("cloud")
        timeout = float(
            model_cfg.get("timeout")
            or M4_MAC_OPTIMIZATION.get("medium_model", {}).get("cloud_timeout", 180)
        )
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=model_cfg.get("base_url", "https://api.deepseek.com/v1"),
            streaming=True,
            max_tokens=model_cfg.get("max_tokens"),
            temperature=model_cfg.get("temperature", 0.4),
            request_timeout=timeout,
            extra_body=dict(model_cfg.get("extra_body") or {}),
        )

    @classmethod
    async def get_cloud_llm(cls, tier: Optional[str] = None) -> ChatOpenAI:
        """Get or create cached Cloud LLM (DeepSeek API) for flash or pro tier."""
        if "cloud" in cls._test_overrides:
            audit_debug("agent.model", "pool_test_override", slot="cloud")
            return cls._test_overrides["cloud"]

        model_name = cls._resolve_cloud_model_name(tier)
        is_pro = "pro" in model_name
        cached = cls._cloud_llm_pro if is_pro else cls._cloud_llm_flash
        if cached is not None:
            audit_debug("agent.model", "pool_cache_hit", slot="cloud", model=model_name)
            return cached

        async with cls._lock:
            cached = cls._cloud_llm_pro if is_pro else cls._cloud_llm_flash
            if cached is not None:
                return cached
            client = await cls._build_cloud_client(model_name)
            if is_pro:
                cls._cloud_llm_pro = client
            else:
                cls._cloud_llm_flash = client
            audit_info(
                "agent.model",
                "pool_instance_created",
                slot="cloud",
                model=model_name,
            )
            return client

    @classmethod
    def clear(cls):
        """Clear cached instances (call when profile or config updates)."""
        cls._small_llm = None
        cls._extraction_llm = None
        cls._cloud_llm_flash = None
        cls._cloud_llm_pro = None
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


async def get_extraction_llm(*, foreground: bool = True) -> ChatOpenAI:
    """Get extraction LLM instance (Gemma-4-E2B, pooled).

    Pass ``foreground=False`` for background callers (memory extraction) that
    manage deferral via ``invoke_medium_background`` instead of the wrapper.
    """
    client = await LLMPool.get_extraction_llm()
    if not foreground:
        return client
    from src.agent.local_llm_scheduler import wrap_medium_for_foreground

    return wrap_medium_for_foreground(client)


async def get_cloud_llm(tier: Optional[str] = None) -> ChatOpenAI:
    """Get cloud LLM instance (DeepSeek API) for optional tier flash|pro."""
    return await LLMPool.get_cloud_llm(tier)
