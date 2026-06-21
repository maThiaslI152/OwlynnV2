import os
import json
import logging
from langchain_core.messages import AIMessage
from src.agent.core.complex_utils.formatter import (
    _strip_dsml_blocks,
    _strip_thinking_tags,
    _TOOL_ONLY_PLACEHOLDERS,
)
from src.api.shared import _TOOL_DESTRUCTIVE_RE, _TOOL_NETWORK_RE, _TOOL_PRIV_RE

logger = logging.getLogger(__name__)


def _sanitize_assistant_text(text: str) -> str:
    """Strip DSML pseudo-tool markup before sending assistant text to the UI."""
    return _strip_dsml_blocks(_strip_thinking_tags(text or ""))


def _is_tool_preamble_text(text: str) -> bool:
    """True when assistant text is only a short tool-running placeholder."""
    cleaned = _sanitize_assistant_text(text).strip()
    if not cleaned:
        return True
    if cleaned in _TOOL_ONLY_PLACEHOLDERS.values():
        return True
    for placeholder in _TOOL_ONLY_PLACEHOLDERS.values():
        # Strip markdown bold markers for comparison
        plain = placeholder.replace("**", "")
        if cleaned == plain or cleaned.startswith(plain.rstrip("…")):
            return True
    if cleaned.lower().startswith("reading workspace file"):
        return True
    if cleaned.lower().startswith("running **") and cleaned.endswith("…"):
        return True
    return False


def _last_ai_message(messages: list) -> AIMessage | None:
    """Pick the newest assistant message from a node output batch."""
    for msg in reversed(messages or []):
        if isinstance(msg, AIMessage):
            return msg
    return None


from src.agent.routing.router import generate_chat_title_router_llm
from src.config.settings import get_project_workspace, normalize_project_id
from src.tools.notebook_libs import parse_chart_artifact
from src.tools.workspace_context import set_active_project_for_run, reset_active_project
from src.config.audit_log import set_thread_id, audit_info


def _files_for_message_content(files: list, base_dir: str) -> list:
    """Expand workspace_ref vision files into inline attachments for multimodal intake."""
    import base64
    import urllib.parse

    from src.api.attachment_intake import infer_mime_from_name, is_vision_filename

    enriched: list = []
    abs_base = os.path.abspath(base_dir)
    for f in files or []:
        if f.get("type") != "workspace_ref":
            enriched.append(f)
            continue
        rel_path = f.get("path") or f.get("name") or ""
        safe_name = urllib.parse.unquote(str(rel_path)).lstrip("/")
        if not safe_name or not is_vision_filename(safe_name):
            enriched.append(f)
            continue
        filepath = os.path.abspath(os.path.join(abs_base, safe_name))
        if not filepath.startswith(abs_base) or not os.path.isfile(filepath):
            enriched.append(f)
            continue
        try:
            with open(filepath, "rb") as fp:
                raw_bytes = fp.read()
            mime = infer_mime_from_name(safe_name)
            enriched.append(
                {
                    "name": os.path.basename(safe_name),
                    "type": mime,
                    "data": base64.b64encode(raw_bytes).decode("ascii"),
                }
            )
        except OSError as exc:
            logger.warning("Failed to load workspace vision ref %s: %s", safe_name, exc)
            enriched.append(f)
    return enriched


def serialize_interrupt_item(item):
    """Convert LangGraph interrupt payload items into JSON-safe values."""
    value = getattr(item, "value", item)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        interrupt_type = value.get("type", "")

        if interrupt_type == "security_approval_required":
            sensitive_calls = value.get("sensitive_tool_calls") or []
            primary_call = (
                sensitive_calls[0]
                if isinstance(sensitive_calls, list) and sensitive_calls
                else {}
            )
            tool_name = str(primary_call.get("name", "unknown"))
            tool_args = _stringify_tool_input(primary_call.get("args"))
            enriched = dict(value)
            enriched["risk_label"] = str(
                primary_call.get("risk_label") or "sensitive_tool_execution"
            )
            enriched["risk_confidence"] = float(
                primary_call.get("risk_confidence", 0.95)
            )
            if primary_call.get("risk_rationale"):
                enriched["risk_rationale"] = str(primary_call.get("risk_rationale"))
            if primary_call.get("remediation_hint"):
                enriched["remediation_hint"] = str(primary_call.get("remediation_hint"))
            enriched["tool_name"] = tool_name
            enriched["tool_args"] = tool_args
            enriched["sensitive_count"] = (
                len(sensitive_calls) if isinstance(sensitive_calls, list) else 0
            )
            return enriched

        if interrupt_type == "plan_review_required":
            # Pass through with enriched context fields for frontend rendering
            enriched = dict(value)
            return enriched

        if interrupt_type == "scope_clarification_required":
            enriched = dict(value)
            return enriched

        if interrupt_type == "ask_user":
            # Pass through; may already have enriched fields from router
            return dict(value)

        return value
    if isinstance(value, list):
        return value
    return str(value)


def _stringify_tool_input(value) -> str | None:
    """Convert tool args payload into a compact UI-safe string."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        return str(value)


def _tool_status_from_content(content: str) -> str:
    """Best-effort status detection for tool outputs."""
    if not isinstance(content, str):
        return "success"
    stripped = content.strip()
    lowered = stripped.lower()
    if lowered.startswith("error:") or lowered.startswith("error "):
        return "error"
    if stripped.startswith("Error:") or stripped.startswith("Error "):
        return "error"
    if lowered.startswith("execution error") or lowered.startswith("sandbox error"):
        return "error"
    if "traceback" in lowered or "permission denied" in lowered:
        return "error"
    if "command not found" in lowered:
        return "error"
    return "success"


def _tool_risk_metadata(tool_name: str, tool_input: str | None) -> dict | None:
    """Best-effort risk metadata for pre-execution tool visibility."""
    hay = f"{tool_name} {tool_input or ''}"
    if _TOOL_DESTRUCTIVE_RE.search(hay) or tool_name == "delete_workspace_file":
        return {
            "risk_label": "destructive_action",
            "risk_confidence": 0.98,
            "risk_rationale": "Delete/drop semantics detected before tool execution.",
            "remediation_hint": "Confirm target path and snapshot before continuing.",
        }
    if _TOOL_NETWORK_RE.search(hay):
        return {
            "risk_label": "network_exfiltration",
            "risk_confidence": 0.9,
            "risk_rationale": "Outbound network indicators detected in tool arguments.",
            "remediation_hint": "Verify destination allowlist and redact sensitive data.",
        }
    if _TOOL_PRIV_RE.search(hay):
        return {
            "risk_label": "privilege_escalation",
            "risk_confidence": 0.92,
            "risk_rationale": "Privilege-elevation markers detected in tool arguments.",
            "remediation_hint": "Run with least privilege and minimal scope.",
        }
    return None
