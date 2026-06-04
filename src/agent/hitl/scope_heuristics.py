"""Scope clarification heuristics for detecting vague build/create requests.

Used by the ``scope_clarify`` node as a cheap first-pass gate before invoking
the Small LLM classifier.
"""

import re

_BUILD_VERBS = {"build", "create", "implement", "make", "develop", "write"}

# Pattern: "build/create/make/write a/an/the/some <something>"
# Catches "build a calculator", "create an API", "write a script", etc.
# without needing an exhaustive noun list.
_BUILD_PATTERN = re.compile(
    r'\b(build|create|make|implement|develop|write)\s+(a|an|the|some|me\s+a)\b',
    re.IGNORECASE,
)

_EXPLICIT_SIGNALS = {
    "language": {"python", "javascript", "typescript", "rust", "go", "java", "c++", "react", "vue", "tkinter", "electron", "next.js", "express", "flask", "django", "fastapi"},
    "ui": {"web", "desktop", "cli", "tui", "terminal", "gui", "browser", "command line", "api"},
    "framework": {"react", "vue", "angular", "svelte", "tkinter", "pyqt", "electron", "tauri"},
}

_CREATIVE_SIGNALS = {"story", "poem", "essay", "review", "explain", "why", "describe"}
_REFACTOR_SIGNALS = {"improve", "refactor", "optimize", "modify", "review", "rewrite", "fix", "update", "improved"}


def needs_clarification(message: str) -> tuple[bool, list[str]]:
    """Heuristic check: does a user message describe an underspecified build request?

    Returns ``(needs_clarification, missing_dimensions)``.
    """
    lowered = message.lower().strip()
    words = set(lowered.split())

    has_build_verb = any(v in words for v in _BUILD_VERBS)
    has_build_pattern = bool(_BUILD_PATTERN.search(lowered))

    if not (has_build_verb or has_build_pattern):
        return False, []

    if any(sig in lowered for sig in _CREATIVE_SIGNALS):
        return False, []

    # Check for refactor signals + code symbols
    has_refactor = any(sig in lowered for sig in _REFACTOR_SIGNALS)
    has_code_symbol = bool(re.search(r'\.(py|js|ts|tsx|jsx|html|css|json|md|rs|go|java|cpp)\b', lowered)) or \
                      "_" in lowered or \
                      "function" in lowered or "class" in lowered
    if has_refactor and has_code_symbol:
        return False, []

    # Skip if message is long and detailed (likely has explicit specs)
    if len(lowered) > 200:
        return False, []

    # Check if it's just a narrow fix/change
    fix_signals = {"fix", "bug", "error", "issue", "line"}
    if any(fix in words for fix in fix_signals):
        return False, []

    missing = []

    # Check language signals
    has_language = any(sig in lowered for sig in _EXPLICIT_SIGNALS["language"])
    if not has_language:
        missing.append("language")

    # Check UI signals
    has_ui = any(sig in lowered for sig in _EXPLICIT_SIGNALS["ui"])
    if not has_ui:
        missing.append("ui_surface")

    # Need at least 2 missing dimensions to trigger
    if len(missing) >= 2:
        return True, missing

    return False, missing
