"""HITL shared policy definitions used by security_proxy and plan_review."""

import re

# Tools that are always safe — information retrieval only, no side effects.
# These bypass HITL entirely: the LLM can call them without approval.
SAFE_TOOLS = {
    "web_search",
    "fetch_webpage",
    "fetch_webpage_dynamic",
    "capture_local_terminal",
    "read_screen_element",
    "get_active_browser_context",
    "capture_kali_terminal",
}

# Tools that always require security review
SENSITIVE_TOOLS = {
    "write_workspace_file",
    "edit_workspace_file",
    "delete_workspace_file",
    "notebook_run",
    "study_note_save",
    "flashcard_deck_create",
}

SENSITIVE_PATTERN_RE = re.compile(
    r"(?:\brm\s+-rf\b|(?:^|[;&|])\s*curl\b|(?:^|[;&|])\s*wget\b|\bsudo\b|\bchmod\b|\bchown\b|\bssh\b|\bscp\b)",
    re.IGNORECASE,
)

_DESTRUCTIVE_RE = re.compile(
    r"(?:\brm\s+-rf\b|\bdrop\b|\bdelete\b|\btruncate\b)", re.IGNORECASE
)
_NETWORK_RE = re.compile(
    r"(?:\bcurl\b|\bwget\b|\bhttp[s]?://\b|\bscp\b|\bssh\b)", re.IGNORECASE
)
_PRIVILEGE_RE = re.compile(r"(?:\bsudo\b|\bchmod\b|\bchown\b)", re.IGNORECASE)

CATEGORY_REMEDIATION = {
    "destructive_action": "Confirm target paths and create a backup/snapshot before execution.",
    "network_exfiltration": "Verify destination/URL allowlist and redact sensitive data before sending.",
    "privilege_escalation": "Run with least privilege and scope command to required files only.",
    "sensitive_tool_execution": "Review tool args carefully and run only if intent is explicit.",
}


def is_mcp_execution_tool(tool_name: str) -> bool:
    """MCP pentest / remote-exec tools require HITL (prefix from defaults.yaml)."""
    from src.config.config_loader import config

    if not config.get("mcp.enabled", True):
        return False
    prefixes = config.get("mcp.sensitive_name_prefixes") or ["pentest_"]
    return any(tool_name.startswith(str(prefix)) for prefix in prefixes)


def is_information_retrieval(tool_name: str) -> bool:
    """Check if a tool is pure information retrieval (no side effects).

    Information-retrieval tools (web_search, fetch_webpage, etc.) are always
    safe to auto-execute. They never mutate state on disk or trigger network
    side effects beyond fetching data for the LLM to read.
    """
    return tool_name in SAFE_TOOLS


def is_sensitive_call(tool_name: str, args) -> bool:
    """Check if a tool call is sensitive based on name and args.

    Sensitive calls require HITL approval. Information-retrieval tools
    (SAFE_TOOLS) are never sensitive regardless of args.
    """
    if is_information_retrieval(tool_name):
        return False
    import json

    if is_mcp_execution_tool(tool_name):
        return True
    if tool_name in SENSITIVE_TOOLS:
        return True
    args_text = (
        json.dumps(args, ensure_ascii=True) if not isinstance(args, str) else args
    )
    return bool(SENSITIVE_PATTERN_RE.search(args_text))
