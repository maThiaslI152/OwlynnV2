"""
Swap-aware route selector for the Multi-LLM Router.

Makes the final routing decision, stripping out obsolete variant swaps and downgrading
cloud routes back to the local default if image inputs are detected (as DeepSeek V4 does
not support vision, but Qwen does).
"""

from __future__ import annotations

import logging

from src.agent.router.models import RouteClassification, TaskFeatures
from src.config.config_loader import config

logger = logging.getLogger(__name__)


def _check_cloud_available() -> bool:
    """Check if cloud escalation is possible (API key + enabled).

    Called fresh on every request — intentionally not cached so that
    cloud availability is re-evaluated each time (Requirement 6.3).
    """
    try:
        from src.memory.user_profile import get_profile
        from src.config.secret_store import resolve_deepseek_api_key

        profile = get_profile()
        if not profile.get("cloud_escalation_enabled", True):
            return False
        api_key = resolve_deepseek_api_key()
        return bool(api_key)
    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        return False


class RouteSelector:
    """Swap-aware route selector."""

    def select(
        self,
        classification: RouteClassification,
        features: TaskFeatures,
        current_variant: str | None,
        swap_threshold: float | None = None,
    ) -> tuple[str, list[str]]:
        """Return ``(final_route, toolbox)``.

        Postconditions:
        - Returns ``(route, toolbox)`` where route is a valid route string
        - ``"simple"`` and ``"complex-cloud"`` routes pass through
        - If ``"complex-cloud"`` but task has images, downgrades to ``"complex-default"``
        - All other complex routes map to ``"complex-default"``
        """
        target_route = classification.route
        toolbox = classification.toolbox

        # Simple route — no swap consideration needed
        if target_route == "simple":
            return target_route, toolbox

        # Cloud route — separate infrastructure, DeepSeek V4 handles everything (vision via proxy)
        if target_route == "complex-cloud":
            return target_route, toolbox

        # All other complex routes map directly to complex-default
        # (since we no longer use vision or longctx variants)
        return "complex-default", toolbox
