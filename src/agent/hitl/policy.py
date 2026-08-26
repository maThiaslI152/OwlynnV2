"""HITL shared policy definitions used by security_proxy and plan_review."""

import re

# Tools that are always safe — information retrieval only, no side effects.
# These bypass HITL entirely: the LLM can call them without approval.
SAFE_TOOLS = {
    "web_search",
    "fetch_webpage",
    "capture_local_terminal",
    "read_screen_element",
    "get_active_browser_context",
    # NOTE: capture_kali_terminal is intentionally NOT here — moved to SENSITIVE_TOOLS
    # because it reads live terminal state that may contain plaintext credentials.
    "wifi_analyze_pcap",
    "wifi_wps_scan",
    "wifi_scan",
    "searchsploit",
    "cve_lookup",
    "subfinder",
    # NOTE: shodan_search and censys_search are intentionally NOT here — moved to
    # SENSITIVE_TOOLS because they make outbound API calls with engagement target data,
    # which constitutes target intelligence exfiltration without user approval.
    "burp_get_issues",
    "poc_generator",
    "cvss_calculator",
    "compliance_mapper",
}

# Tools that always require security review
SENSITIVE_TOOLS = {
    "write_workspace_file",
    "edit_workspace_file",
    "delete_workspace_file",
    "notebook_run",
    "study_note_save",
    "flashcard_deck_create",
    "wifi_deauth",
    "wifi_handshake_capture",
    "nmap_scan",
    "masscan_scan",
    "service_enum",
    "nikto_scan",
    "gobuster_scan",
    "sqlmap_scan",
    "header_check",
    "nuclei_scan",
    "metasploit_run",
    "poc_validate",
    "privesc_check",
    "credential_harvest",
    "bloodhound_run",
    "kerberoast",
    "ldap_enum",
    "hydra_attack",
    "john_crack",
    "s3_enum",
    "burp_scan_target",
    "hackerone_submit",
    # Moved from SAFE_TOOLS — makes outbound API calls with target intelligence
    "shodan_search",
    "censys_search",
    # Moved from SAFE_TOOLS — reads live terminal state that may contain credentials
    "capture_kali_terminal",
    # Browser bridge — screenshots / cookie-backed downloads can leak secrets
    "get_active_browser_screenshot",
    "download_to_workspace",
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

    # get_html returns raw DOM (may include PII / form values) — require HITL
    if tool_name == "active_browser_action":
        action = ""
        if isinstance(args, dict):
            action = str(args.get("action") or "")
        elif isinstance(args, str):
            action = args
        if action.strip().lower() == "get_html":
            return True

    args_text = (
        json.dumps(args, ensure_ascii=True) if not isinstance(args, str) else args
    )
    return bool(SENSITIVE_PATTERN_RE.search(args_text))
