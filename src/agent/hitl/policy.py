"""HITL shared policy definitions used by security_proxy and plan_review."""

# Tools that always require security review
SENSITIVE_TOOLS = {
    "write_workspace_file",
    "edit_workspace_file",
    "delete_workspace_file",
    "notebook_run",
}

import re

SENSITIVE_PATTERN_RE = re.compile(
    r"(?:\brm\s+-rf\b|(?:^|[;&|])\s*curl\b|(?:^|[;&|])\s*wget\b|\bsudo\b|\bchmod\b|\bchown\b|\bssh\b|\bscp\b)",
    re.IGNORECASE,
)

_DESTRUCTIVE_RE = re.compile(r"(?:\brm\s+-rf\b|\bdrop\b|\bdelete\b|\btruncate\b)", re.IGNORECASE)
_NETWORK_RE = re.compile(r"(?:\bcurl\b|\bwget\b|\bhttp[s]?://\b|\bscp\b|\bssh\b)", re.IGNORECASE)
_PRIVILEGE_RE = re.compile(r"(?:\bsudo\b|\bchmod\b|\bchown\b)", re.IGNORECASE)

CATEGORY_REMEDIATION = {
    "destructive_action": "Confirm target paths and create a backup/snapshot before execution.",
    "network_exfiltration": "Verify destination/URL allowlist and redact sensitive data before sending.",
    "privilege_escalation": "Run with least privilege and scope command to required files only.",
    "sensitive_tool_execution": "Review tool args carefully and run only if intent is explicit.",
}


def is_sensitive_call(tool_name: str, args) -> bool:
    """Check if a tool call is sensitive based on name and args."""
    import json
    if tool_name in SENSITIVE_TOOLS:
        return True
    args_text = json.dumps(args, ensure_ascii=True) if not isinstance(args, str) else args
    return bool(SENSITIVE_PATTERN_RE.search(args_text))
