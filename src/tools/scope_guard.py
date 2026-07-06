"""Scope enforcement guard for pentest mode.

Validates that tool execution targets are within the engagement's defined scope.
Integrates with security_proxy_node to block or warn on out-of-scope targets.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from src.memory.pentest_engagement import get_active_engagement, validate_target

logger = logging.getLogger(__name__)

# Patterns to extract targets from tool arguments
_IP_RE = re.compile(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?:/\d{1,2})?)\b")
_DOMAIN_RE = re.compile(
    r"\b([a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?(?:\.[a-zA-Z]{2,})+)\b"
)
_URL_RE = re.compile(r"https?://([^\s/:]+)")

# Destructive commands that should always require HITL, even without an active engagement
_DESTRUCTIVE_CMD_RE = re.compile(
    r"\brm\s+-rf\s+/\b"
    r"|\bmkfs\b"
    r"|\bdd\s+if=.*of=/dev/"
    r"|\b:\(\)\{.*\|.*&\s*\};\s*:"  # fork bomb
    r"|\bchmod\s+-R\s+777\s+/"
    r"|\bshutdown\b"
    r"|\breboot\b"
    r"|\binit\s+0\b",
    re.IGNORECASE,
)


def extract_targets_from_args(tool_name: str, args: dict) -> list[str]:
    """Extract target IPs/hostnames from tool call arguments.

    Returns a list of target strings that should be validated against scope.
    """
    targets: list[str] = []

    # Tools that take explicit target parameters
    target_fields = ["target", "host", "hostname", "ip", "url", "selector"]
    for field in target_fields:
        val = args.get(field, "")
        if val and isinstance(val, str):
            targets.extend(_extract_from_text(val))

    # For command-based tools, extract from command strings
    command = args.get("command", "") or args.get("text", "") or args.get("session", "")
    if command and isinstance(command, str):
        targets.extend(_extract_from_text(command))

    # Deduplicate
    return list(dict.fromkeys(targets))


def _extract_from_text(text: str) -> list[str]:
    """Extract IPs and hostnames from arbitrary text."""
    targets = []
    # URLs first
    for match in _URL_RE.finditer(text):
        host = match.group(1)
        if host and host not in ("localhost", "127.0.0.1"):
            targets.append(host)
    # IPs/CIDRs
    for match in _IP_RE.finditer(text):
        ip = match.group(1)
        if ip and ip not in ("0.0.0.0", "127.0.0.1", "255.255.255.255"):
            targets.append(ip)
    # Domains (only if no IPs found, to avoid noise)
    if not targets:
        for match in _DOMAIN_RE.finditer(text):
            domain = match.group(1)
            if domain and "." in domain and not domain.endswith(".local"):
                targets.append(domain)
    return targets


def check_scope(engagement_id: str, targets: list[str]) -> tuple[bool, str]:
    """Validate targets against engagement scope.

    Returns (allowed, reason).
    - allowed=True: all targets are in scope
    - allowed=False: one or more targets are out of scope or excluded
    """
    if not targets:
        return True, "No targets to validate"

    for target in targets:
        allowed, reason = validate_target(engagement_id, target)
        if not allowed:
            return False, reason

    return True, "All targets in scope"


def guard_tool_call(tool_name: str, args: dict) -> tuple[bool, str]:
    """Main entry point: check if a tool call's targets are in scope.

    Returns (allowed, reason).
    Only checks when an active engagement exists. Non-pentest calls pass through.
    Always blocks obviously destructive commands regardless of engagement state.
    """
    # Always block catastrophic commands, even without an active engagement
    command = args.get("command", "") or args.get("text", "") or ""
    if isinstance(command, str) and _DESTRUCTIVE_CMD_RE.search(command):
        return False, (
            f"Destructive command detected: '{command[:80]}'. "
            "This command can cause irreversible damage and is blocked by policy."
        )

    eng = get_active_engagement()
    if not eng:
        return True, "No active engagement (non-pentest mode)"

    targets = extract_targets_from_args(tool_name, args)
    if not targets:
        return True, "No extractable targets in tool args"

    return check_scope(eng["id"], targets)
