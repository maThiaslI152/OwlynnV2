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


def _build_local_llm_client(
    *,
    temperature: float = 0.2,
    max_tokens: int | None = None,
    max_output_tokens: int = 512,
    timeout: float = 10,
) -> ChatOpenAI:
    """Build a ChatOpenAI client for the local model (LM Studio).

    Reads all config from models.small.* in defaults.yaml via get_model_config().
    Individual parameters override the config defaults for slot-specific tuning.
    """
    model_cfg = get_model_config("small")
    extra_body = dict(model_cfg.get("extra_body") or {})
    extra_body["max_output_tokens"] = model_cfg.get(
        "max_output_tokens", max_output_tokens
    )
    return ChatOpenAI(
        model=model_cfg.get("model_name", config.get_small_model_name()),
        api_key="sk-local-no-key-needed",
        base_url=model_cfg.get("base_url", "http://127.0.0.1:1234/v1"),
        temperature=model_cfg.get("temperature", temperature),
        max_tokens=max_tokens or model_cfg.get("max_tokens"),
        extra_body=extra_body,
        request_timeout=model_cfg.get("request_timeout")
        or model_cfg.get("timeout", timeout),
        stream_chunk_timeout=None,
    )


class LLMPool:
    """Singleton pool for LLM instances to avoid re-initialization overhead."""

    _small_llm: Optional[ChatOpenAI] = None
    _fallback_llm: Optional[ChatOpenAI] = None
    _pentest_llm: Optional[ChatOpenAI] = None

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
                        cls._small_llm = _build_local_llm_client()
                        audit_info(
                            "agent.model",
                            "pool_instance_created",
                            slot="small",
                            model=get_model_config("small").get("model_name"),
                        )
            except Exception as e:
                logger.warning("Error suppressed: %s", e)
                audit_info(
                    "agent.model",
                    "pool_instance_created",
                    slot="small",
                    model=get_model_config("small").get("model_name"),
                    source="fallback",
                )
                return _build_local_llm_client()
        else:
            audit_debug("agent.model", "pool_cache_hit", slot="small")
        return cls._small_llm

    # ── extraction (unified local model) ──────────────────────────

    @classmethod
    async def get_extraction_llm(cls, *, foreground: bool = True) -> ChatOpenAI:
        """Get or create cached extraction LLM instance. Maps to small LLM in unified architecture."""
        if "extraction" in cls._test_overrides:
            return cls._test_overrides["extraction"]
        return await cls.get_small_llm()

    # ── fallback (same model as small, used when cloud fails) ─────

    @classmethod
    async def get_fallback_llm(cls) -> ChatOpenAI:
        """Get or create cached fallback LLM instance.

        Uses the same local model as small but with expanded context and timeout
        suitable for complex task fallback when cloud is unavailable.
        """
        if "fallback" in cls._test_overrides:
            audit_debug("agent.model", "pool_test_override", slot="fallback")
            return cls._test_overrides["fallback"]
        _FALLBACK_DEFAULTS = dict(
            temperature=0.1,
            max_tokens=8192,
            max_output_tokens=8192,
            timeout=180,
        )
        if cls._fallback_llm is None:
            try:
                async with cls._lock:
                    if cls._fallback_llm is None:
                        cls._fallback_llm = _build_local_llm_client(
                            **_FALLBACK_DEFAULTS
                        )
                        audit_info(
                            "agent.model",
                            "pool_instance_created",
                            slot="fallback",
                            model=get_model_config("small").get("model_name"),
                        )
            except Exception as e:
                logger.warning("Fallback LLM creation error: %s", e)
                return _build_local_llm_client(**_FALLBACK_DEFAULTS)
        else:
            audit_debug("agent.model", "pool_cache_hit", slot="fallback")
        return cls._fallback_llm

    # ── pentest (dedicated pentest model) ──────────────────────────────

    @classmethod
    async def get_pentest_llm(cls) -> ChatOpenAI:
        """Get or create cached pentest LLM instance.

        Uses the dedicated pentest model configured in models.pentest.* in defaults.yaml.
        Falls back to small model if no pentest model is configured.
        """
        if "pentest" in cls._test_overrides:
            audit_debug("agent.model", "pool_test_override", slot="pentest")
            return cls._test_overrides["pentest"]
        _PENTEST_DEFAULTS = dict(
            temperature=0.3,
            max_tokens=8192,
            max_output_tokens=8192,
            timeout=180,
        )
        if cls._pentest_llm is None:
            try:
                async with cls._lock:
                    if cls._pentest_llm is None:
                        model_cfg = get_model_config("pentest")
                        pentest_model_name = config.get_pentest_model_name()
                        extra_body = dict(model_cfg.get("extra_body") or {})
                        extra_body["max_output_tokens"] = model_cfg.get(
                            "max_output_tokens", _PENTEST_DEFAULTS["max_output_tokens"]
                        )
                        cls._pentest_llm = ChatOpenAI(
                            model=pentest_model_name,
                            api_key="sk-local-no-key-needed",
                            base_url=model_cfg.get(
                                "base_url", "http://127.0.0.1:1234/v1"
                            ),
                            temperature=model_cfg.get(
                                "temperature", _PENTEST_DEFAULTS["temperature"]
                            ),
                            max_tokens=model_cfg.get(
                                "max_tokens", _PENTEST_DEFAULTS["max_tokens"]
                            ),
                            extra_body=extra_body,
                            request_timeout=model_cfg.get("request_timeout")
                            or model_cfg.get("timeout", _PENTEST_DEFAULTS["timeout"]),
                            stream_chunk_timeout=None,
                        )
                        audit_info(
                            "agent.model",
                            "pool_instance_created",
                            slot="pentest",
                            model=pentest_model_name,
                        )
            except Exception as e:
                logger.warning("Pentest LLM creation error: %s", e)
                return _build_local_llm_client(**_PENTEST_DEFAULTS)
        else:
            audit_debug("agent.model", "pool_cache_hit", slot="pentest")
        return cls._pentest_llm

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
            config.get("models.cloud.model_name")
            or profile.get("cloud_llm_model_name")
            or tiers.get("flash")
            or config.get_cloud_model_name()
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
        cls._fallback_llm = None
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
    """Get extraction LLM instance (unified local model, pooled).

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


async def get_pentest_llm() -> ChatOpenAI:
    """Get pentest LLM instance (dedicated pentest model, local-only)."""
    return await LLMPool.get_pentest_llm()


async def get_fallback_llm() -> ChatOpenAI:
    """Get fallback LLM instance (local model, expanded context for complex tasks)."""
    return await LLMPool.get_fallback_llm()
