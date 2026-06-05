import asyncio
import json
import logging
from typing import Any
import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.prebuilt import ToolNode

from src.agent.state import AgentState
from src.agent.llm import get_medium_llm, get_cloud_llm, CloudUnavailableError
from src.agent.response_styles import style_instruction_for_prompt
from src.agent.tool_sets import (
    COMPLEX_TOOLS_NO_WEB,
    COMPLEX_TOOLS_WITH_WEB,
    resolve_tools,
)
from src.agent.lm_studio_compat import is_local_server, with_system_for_local_server
from src.agent.anonymization import anonymize, deanonymize

from .complex_utils.fallback import _fallback_for_blank_response
from .complex_utils.formatter import _strip_thinking_tags, _flatten_human_content
from src.agent.hitl.cloud_brief import build_cloud_brief, estimate_brief_tokens
from src.memory.user_profile import get_profile

logger = logging.getLogger(__name__)

from src.config.audit_log import audit_debug
from src.config.log_middleware import log_model_attempt, log_node
from src.config.config_loader import config

# Context window for the local model (sourced from centralized config)
# Minimum output tokens — if less than this is available, we still try
_MIN_OUTPUT_TOKENS = int(config.get("complex.min_output_tokens", 512))
# Safety margin to avoid hitting the exact limit
_CONTEXT_SAFETY_MARGIN = int(config.get("complex.context_safety_margin", 256))

# Maximum number of automatic continuation rounds when the LLM hits its token budget
MAX_CUTOFF_RETRIES = int(config.get("complex.max_cutoff_retries", 1))

# Max retries for cloud LLM calls with exponential backoff
_MAX_CLOUD_RETRIES = int(config.get("complex.max_cloud_retries", 3))


async def _invoke_with_cloud_retry(
    bound_llm, prompt_messages, *, fallback_chain, model_label, route
):
    """Invoke cloud LLM with circuit breaker check, retry logic, and cost tracking.

    Retries on 429 (rate limit) and 5xx (server errors) with exponential
    backoff. Does **not** retry on 401 (auth errors).  Respects the
    circuit breaker — raises immediately if the circuit is open.
    """
    from src.agent.cloud_circuit_breaker import get_circuit_breaker

    breaker = get_circuit_breaker()
    if breaker.is_open():
        raise Exception("Circuit breaker open")

    last_error = None

    for attempt in range(_MAX_CLOUD_RETRIES + 1):
        try:
            response = await bound_llm.ainvoke(prompt_messages)
            breaker.record_success()
            return response
        except Exception as e:
            last_error = e
            err_str = str(e)

            if "401" in err_str:
                breaker.record_failure()
                raise

            is_retryable = "429" in err_str or any(
                code in err_str for code in ("500", "502", "503", "504")
            )
            if not is_retryable or attempt >= _MAX_CLOUD_RETRIES:
                breaker.record_failure()
                raise

            wait = 2**attempt
            await asyncio.sleep(wait)

    breaker.record_failure()
    raise last_error if last_error else Exception("Cloud retry exhausted")


def _estimate_message_tokens(messages: list) -> int:
    """
    Estimate token count for a list of LangChain messages.
    Uses a rough heuristic: ~4 chars per token for English/code,
    ~2 chars per token for Thai/CJK.  Good enough for budget capping
    without needing a real tokenizer (which would add latency).
    """
    total_chars = 0
    for msg in messages:
        content = getattr(msg, "content", None) or ""
        if isinstance(content, list):
            for block in content:
                if isinstance(block, str):
                    total_chars += len(block)
                elif isinstance(block, dict):
                    total_chars += len(str(block.get("text", "")))
        else:
            total_chars += len(str(content))
        # Overhead per message (role tokens, formatting)
        total_chars += 20

    # Heuristic: average ~3.5 chars per token (blend of English and Thai)
    return int(total_chars / 3.5)


def _cap_budget_to_context(prompt_messages: list, requested_budget: int, max_context: int) -> int:
    """
    Given the assembled prompt and a requested output budget, cap it so that
    input + output doesn't exceed the context window.
    """
    input_tokens = _estimate_message_tokens(prompt_messages)
    available = max_context - input_tokens - _CONTEXT_SAFETY_MARGIN
    capped = max(min(requested_budget, available), _MIN_OUTPUT_TOKENS)
    return capped


def _total_prompt_tokens(prompt_messages: list) -> int:
    """Estimate total tokens in the assembled prompt."""
    return _estimate_message_tokens(prompt_messages)


_HARD_PROMPT_LIMIT_RATIO = (
    0.85  # Max 85% of context window for prompt (leaves 15% for response)
)


def _needs_prompt_truncation(prompt_messages: list, max_context: int) -> bool:
    """Check if the prompt exceeds the hard safety limit for the model context."""
    total = _estimate_message_tokens(prompt_messages)
    limit = int(max_context * _HARD_PROMPT_LIMIT_RATIO)
    return total > limit


COMPLEX_PROMPT = """### Identity
You are Owlynn, an expert reasoning agent. For complex tasks (code, math, multi-step work): think step by step before answering. For simple questions, greetings, or small talk: answer concisely without lengthy preamble.
Current date: {current_date}

### Behaviors
- If a request is clearly ambiguous or missing critical details, use ask_user once to clarify. If you can reasonably infer intent from context or memory, just do the work. Don't over-ask.
- When a request matches a known skill, call invoke_skill to get the workflow and follow it. Use list_skills to see available skills if unsure.
- Match your verbosity to the task: be thorough for complex work, be concise for simple questions.
- If project instructions are provided below, they take HIGHEST PRIORITY. Tailor your tone, focus, and approach to match the project's purpose.

User memory context:
{memory_context}

### Guidelines
- If writing code, include comments
- When reasoning through a genuinely complex problem, show your thinking. Skip elaborate reasoning for trivial questions.
- Never fabricate facts — if uncertain, say so{style_hint}

Agent persona (for context only — do NOT echo or describe):
{persona}"""

# Models sometimes mimic bracketed "use tool X" system text instead of emitting real tool_calls; forbid that.
_TOOL_CALL_DISCIPLINE = """
[CRITICAL INSTRUCTION]: You have native function/tool calling in this API. Whenever you need file contents, web results, or sandbox code, you **MUST** emit an actual JSON tool/function call; the UI executes it automatically. Do **NOT** answer with only prose like "I will use the read_workspace_file tool" or echo bracketed instructions — actually CALL the tool using the native tool calling schema, wait for results, then write your answer from those results. DO NOT output markdown code blocks containing JSON like `\u200b`\u200b`json {"name": "..."}`\u200b`\u200b`. You must use the native tool binding. Failure to emit tool calls when required is a critical error."""

COMPLEX_TOOL_GUIDANCE_WEB = (
    """
### Tools
web_search, fetch_webpage — web lookup and page reading
read_workspace_file, write_workspace_file, edit_workspace_file, list_workspace_files, delete_workspace_file — file management
notebook_run, notebook_reset — Python REPL (use f"{WORKSPACE_DIR}/filename.csv" for paths)
create_docx, create_xlsx, create_pptx, create_pdf — document generation
recall_memories, recall_all_memories, forget_memory — memory search and management
todo_add, todo_list, todo_complete — task tracking
list_skills, invoke_skill — skill templates
ask_user — ask the user a clarifying question

### Capability Affirmations (Anti-Refusal)
You are equipped with powerful tools that override your standard AI limitations. NEVER claim you cannot do the following:
- **Visualizations/Charts**: You CAN generate images, plots, and charts. Use `notebook_run` to write Python code (matplotlib, seaborn), save the plot to WORKSPACE_DIR, and embed it as a markdown image.
- **Document Generation**: You CAN create documents. Use `create_docx`, `create_xlsx`, `create_pptx`, and `create_pdf` to fulfill these requests.
- **File System**: You CAN read, write, edit, and manage files in the user's workspace using the `_workspace_file` tools.
- **Internet Access**: You CAN browse the live internet. Use `web_search` and `fetch_webpage` for current events or unknown information instead of citing a knowledge cutoff.

### Rules
- Ground all claims in tool output. Never invent facts or URLs.
- After web_search, if the search snippets are too brief to answer the user's question, call fetch_webpage on the most relevant result URLs to get the full page content.
- Use [1] [2] citations from fetch_webpage excerpts.
- If tools return nothing useful, say so honestly.
- Prefer workspace files and project knowledge over web search for project-specific work.
- If browser MCP tools (browser_snapshot, browser_take_screenshot, etc.) are available, use them when the user asks what's on a web page or in their browser window."""
    + _TOOL_CALL_DISCIPLINE
)

COMPLEX_TOOL_GUIDANCE_NO_WEB = (
    """
### Tools (web search is off for this chat)
read_workspace_file, write_workspace_file, edit_workspace_file, list_workspace_files, delete_workspace_file — file management
notebook_run, notebook_reset — Python REPL (use f"{WORKSPACE_DIR}/filename.csv" for paths)
create_docx, create_xlsx, create_pptx, create_pdf — document generation
recall_memories, recall_all_memories, forget_memory — memory search and management
todo_add, todo_list, todo_complete — task tracking
list_skills, invoke_skill — skill templates
ask_user — ask the user a clarifying question

### Capability Affirmations (Anti-Refusal)
You are equipped with powerful tools that override your standard AI limitations. NEVER claim you cannot do the following:
- **Visualizations/Charts**: You CAN generate images, plots, and charts. Use `notebook_run` to write Python code (matplotlib, seaborn), save the plot to WORKSPACE_DIR, and embed it as a markdown image.
- **Document Generation**: You CAN create documents. Use `create_docx`, `create_xlsx`, `create_pptx`, and `create_pdf` to fulfill these requests.
- **File System**: You CAN read, write, edit, and manage files in the user's workspace using the `_workspace_file` tools.

### Rules
Summarize tool results clearly for the user."""
    + _TOOL_CALL_DISCIPLINE
)

from .complex_utils.helpers import _web_search_tool_output_has_results


def build_web_search_answer_nudge_messages(tool_messages: list) -> list[HumanMessage]:
    """After a successful web_search, remind the model it must write the final answer (non-empty)."""
    if not tool_messages:
        return []
    for m in tool_messages:
        if not isinstance(m, ToolMessage):
            continue
        if (getattr(m, "name", None) or "") != "web_search":
            continue
        c = m.content if isinstance(m.content, str) else str(m.content or "")
        if not _web_search_tool_output_has_results(c):
            continue
        return [
            HumanMessage(
                content=(
                    "[Internal reminder for assistant] **web_search** returned results above. "
                    "You must now write a complete answer for the user in plain language using those "
                    "results (definition, main ideas, optional link to the official docs). "
                    "Do not reply with empty content or only tool metadata."
                )
            )
        ]
    return []


def build_fetch_retry_nudge_messages(tool_messages: list) -> list[HumanMessage]:
    """
    If fetch_webpage clearly failed or only returned SPA metadata, append a one-shot user-role
    reminder so the next LLM turn retries fetch_webpage_dynamic or another search hit.
    """
    if not tool_messages:
        return []
    need_dynamic = False
    need_alt_url = False
    for m in tool_messages:
        if not isinstance(m, ToolMessage):
            continue
        if (getattr(m, "name", None) or "") != "fetch_webpage":
            continue
        c = m.content if isinstance(m.content, str) else str(m.content or "")
        if (
            "[fetch_webpage] No extractable text" in c
            or "[Note: Page body is mostly empty in static HTML" in c
        ):
            need_dynamic = True
        if c.startswith("[fetch_webpage] HTTP error"):
            need_alt_url = True
    out: list[HumanMessage] = []
    if need_dynamic:
        out.append(
            HumanMessage(
                content=(
                    "[Internal reminder for assistant] Static **fetch_webpage** returned no usable article body "
                    "(empty HTML or SPA shell). Before answering the user, call **fetch_webpage_dynamic** with the "
                    "same URL, or **fetch_webpage** a different URL from **web_search** results."
                )
            )
        )
    elif need_alt_url:
        out.append(
            HumanMessage(
                content=(
                    "[Internal reminder for assistant] **fetch_webpage** failed with an HTTP error. "
                    "Open another result from **web_search** instead of repeating the same URL."
                )
            )
        )
    return out


def _latest_user_text(messages: list) -> str:
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            return _flatten_human_content(m.content)
    return ""


def _workspace_paths_from_text(text: str) -> list[str]:
    """Filenames from chat upload injections (server + legacy wording)."""
    paths: list[str] = []
    seen: set[str] = set()
    for pat in (
        r"\[Workspace file\s+`([^`]+)`",
        r"Workspace file\s+`([^`]+)`",
        r"\[File:\s*([^\]\n]+?)\s+uploaded to workspace",
    ):
        for m in re.finditer(pat, text, re.IGNORECASE):
            p = (m.group(1) or "").strip()
            if p and p not in seen:
                seen.add(p)
                paths.append(p)
    return paths


def _user_intent_needs_workspace_read(text: str) -> bool:
    t = (text or "").lower()
    needles = (
        "summarize",
        "summary",
        "study",
        "read this",
        "read the",
        "explain",
        "what does",
        "what is",
        "help me",
        "tell me",
        "analyze",
        "slide",
        "pdf",
        "document",
        "this file",
        "lecture",
        "chapter",
        "content of",
        "outline",
        "key point",
        "notes",
    )
    return any(n in t for n in needles)


def _looks_like_prose_tool_stall(response: AIMessage) -> bool:
    """Local models often answer with 'use read_workspace_file…' instead of tool_calls."""
    if getattr(response, "tool_calls", None):
        return False
    c = str(getattr(response, "content", "") or "").strip()
    if not c:
        return True
    low = c.lower()
    if "read_workspace_file" in low:
        return True
    if "uploaded to workspace" in low and ("tool" in low or "read_" in low):
        return True
    if len(c) < 420:
        return True
    return False


async def _auto_read_workspace_bundle(paths: list[str]) -> str:
    """Read files via the same tool implementation the graph uses (thread pool)."""
    from src.tools.core_tools import read_workspace_file

    sections: list[str] = []
    # With 100k context, we can afford more content per file
    per_cap = 28_000
    for raw in paths[:3]:
        p = raw.strip()
        if not p:
            continue
        try:
            body = await asyncio.to_thread(read_workspace_file.invoke, {"filename": p})
        except Exception as e:
            import logging; logging.debug("Silent error suppressed: %s", e)
            body = f"[read_workspace_file error for {p!r}: {e}]"
        b = str(body)
        if len(b) > per_cap:
            b = (
                b[:per_cap]
                + f"\n\n[Truncated after {per_cap} characters; full file remains in the workspace.]"
            )
        sections.append(f"### File: {p}\n{b}")
    if not sections:
        return ""
    return (
        "[Automated workspace read — files were read by the host because the model did not emit "
        "tool calls. Use ONLY the text below to answer the user now — do not ask them to run a tool.]\n\n"
        + "\n\n".join(sections)
    )


def _trim_tool_history(messages: list, max_tool_cycles: int = 6) -> list:
    """
    Compress older tool call/result cycles to keep the conversation within
    the context window.  Keeps the first human message and the last
    `max_tool_cycles` full cycles (AI tool_call + ToolMessage pairs).
    Older tool results are replaced with a one-line summary.
    """
    if len(messages) <= 6:
        return messages  # Short enough, no trimming needed

    # Find all tool message indices
    tool_indices = [i for i, m in enumerate(messages) if isinstance(m, ToolMessage)]
    if len(tool_indices) <= max_tool_cycles:
        return messages  # Few enough cycles, keep all

    # Indices of tool messages to summarize (all except the last N)
    old_tool_indices = set(tool_indices[:-max_tool_cycles])

    # Also find the AI messages that triggered those old tool calls
    old_ai_indices = set()
    for ti in old_tool_indices:
        # The AI message with tool_calls is typically right before the tool message(s)
        for j in range(ti - 1, -1, -1):
            if isinstance(messages[j], AIMessage) and getattr(
                messages[j], "tool_calls", None
            ):
                old_ai_indices.add(j)
                break

    trimmed = []
    for i, msg in enumerate(messages):
        if i in old_tool_indices:
            # Replace old tool output with a compact summary
            content = (
                msg.content if isinstance(msg.content, str) else str(msg.content or "")
            )
            tool_name = getattr(msg, "name", "tool") or "tool"
            if "Error" in content[:100]:
                summary = f"[{tool_name}: returned an error]"
            else:
                summary = f"[{tool_name}: completed, {len(content)} chars output]"
            trimmed.append(
                ToolMessage(
                    content=summary,
                    tool_call_id=msg.tool_call_id,
                    name=getattr(msg, "name", None),
                )
            )
        elif i in old_ai_indices:
            # Keep the AI message but it needs to stay for the tool_call_id chain
            trimmed.append(msg)
        else:
            trimmed.append(msg)

    return trimmed


@log_node("complex_llm")
async def complex_llm_node(state: AgentState) -> AgentState:
    """
    LLM reasoning node for the cyclic secure tool flow.
    It either answers directly or emits tool calls for the security proxy.

    Supports route-based model selection (9.1), cloud anonymization (9.2),
    dynamic tool binding (9.3), tiered fallback chains (9.4), and
    cloud token usage tracking (9.5).
    """
    memory_context = state.get("memory_context", "None")
    persona = state.get("persona", "No persona available")
    mode = state.get("mode") or "tools_on"
    thread_messages = list(state.get("messages") or [])

    web_on = state.get("web_search_enabled")
    if web_on is None:
        web_on = True
    web_on = bool(web_on)

    style_hint = style_instruction_for_prompt(state.get("response_style"))
    security_decision = state.get("security_decision")
    security_reason = state.get("security_reason")

    system_text = COMPLEX_PROMPT.format(
        current_date=__import__("datetime").date.today().strftime("%B %d, %Y"),
        memory_context=memory_context,
        persona=persona,
        style_hint=style_hint,
    )
    if mode != "tools_off":
        system_text += (
            COMPLEX_TOOL_GUIDANCE_WEB if web_on else COMPLEX_TOOL_GUIDANCE_NO_WEB
        )

    if security_decision == "denied":
        system_text += (
            "\n\nSecurity notice: A previous tool request was denied. "
            "Do not retry the blocked operation. Suggest a safer alternative or explain why it was blocked."
        )
        if security_reason:
            system_text += f"\nBlocked reason: {security_reason}"

    denied_tools = state.get("denied_tools") or []
    if denied_tools:
        system_text += (
            f"\n\nBLOCKED TOOLS (do NOT call these): {', '.join(denied_tools)}"
        )

    # ── Inject user-approved clarified_scope if present ────────────────────
    clarified_scope = state.get("clarified_scope")
    if (
        clarified_scope
        and isinstance(clarified_scope, dict)
        and not clarified_scope.get("skipped")
    ):
        scope_lines = ["\n\nCONFIRMED REQUIREMENTS (user-approved, do not contradict):"]
        for key, value in clarified_scope.items():
            if key in ("skipped", "_raw", "_source"):
                continue
            if isinstance(value, dict):
                label = value.get("label", str(value))
                user_input = value.get("user_input", "")
                scope_lines.append(
                    f"- {key}: {label}" + (f" ({user_input})" if user_input else "")
                )
            else:
                scope_lines.append(f"- {key}: {value}")
        system_text += "\n".join(scope_lines)

    # ── Web search suggestion from scope_clarify bypass ────────────────────
    if state.get("web_search_suggested") and web_on:
        system_text += (
            "\n\nThe user's question is informational and may require current web data. "
            "Use web_search to find relevant information before answering. "
            "If search snippets are insufficient, call fetch_webpage on result URLs "
            "to get full page content."
        )

    # ── Cutoff continuation: LLM was cut off — pick up where it stopped ────
    _cutoff_round = state.get("_cutoff_round", 0)
    if state.get("_cutoff_pending") and _cutoff_round > 0:
        system_text += (
            "\n\nYour previous response was cut off (token budget exceeded). "
            "Continue from where you stopped. Do NOT repeat what you already wrote. "
            "Pick up mid-sentence if needed and complete your thought."
        )

    system = SystemMessage(content=system_text)

    # Trim conversation history to fit context window.
    trimmed_messages = _trim_tool_history(thread_messages)

    # ── 9.1: Route-based model selection ─────────────────────────────────
    route = state.get("route") or "complex-default"
    if route == "complex-cloud":
        max_context = int(config.get("models.cloud.context_window", 1048576))
    else:
        max_context = int(config.get("models.medium.context_window", 16384))
    model_label = "medium-default"
    anon_mapping = None
    api_tokens = None
    profile = get_profile()

    # Keep a pre-anonymization copy for cloud fallback paths.
    original_trimmed_messages = list(trimmed_messages)

    # ── 9.2: Anonymization for cloud route ───────────────────────────────
    if route == "complex-cloud" and profile.get("cloud_anonymization_enabled", True):
        anon_ctx = {
            "name": profile.get("name", ""),
            "custom_sensitive_terms": profile.get("custom_sensitive_terms", []),
        }
        # Anonymize system text
        system_text, anon_mapping = anonymize(system_text, anon_ctx)
        system = SystemMessage(content=system_text)
        # Anonymize each message content
        import copy

        anon_messages = []
        for msg in trimmed_messages:
            content = msg.content
            if isinstance(content, str):
                content, msg_mapping = anonymize(content, anon_ctx)
                if anon_mapping is not None:
                    anon_mapping.update(msg_mapping)
                else:
                    anon_mapping = msg_mapping
            new_msg = copy.copy(msg)
            new_msg.content = content
            anon_messages.append(new_msg)
        trimmed_messages = anon_messages

    # ── 9.3: Cloud brief (compact, anonymized prompt for DeepSeek) ────────
    cloud_brief_tokens_est = 0
    anonymization_placeholders_count = 0
    if route == "complex-cloud" and profile.get("cloud_brief_enabled", True):
        # Build plan_review summary from state
        plan_review_summary: dict[str, Any] | None = None
        if state.get("plan_review_approved") is not None:
            plan_review_summary = {
                "approved": bool(state.get("plan_review_approved")),
                "stated_intent": state.get("plan_review_feedback") or "Plan reviewed",
                "pitfalls": [],
            }

        # Extract last user message and last assistant summary
        last_user_message = ""
        last_assistant_summary = ""
        for msg in reversed(thread_messages):
            if isinstance(msg, HumanMessage) and not last_user_message:
                last_user_message = str(msg.content)
            if isinstance(msg, AIMessage) and not last_assistant_summary:
                content = str(msg.content)
                # Truncate long assistant responses to just a summary line
                last_assistant_summary = (
                    content[:300] if len(content) > 300 else content
                )
            if last_user_message and last_assistant_summary:
                break

        # Build memory context from state
        memory_context = ""
        if state.get("memory_context"):
            mc = state.get("memory_context")
            memory_context = str(mc) if isinstance(mc, str) else json.dumps(mc)

        # Build the brief
        brief = build_cloud_brief(
            clarified_scope=state.get("clarified_scope"),
            plan_review_summary=plan_review_summary,
            memory_context=memory_context,
            last_user_message=last_user_message,
            last_assistant_summary=last_assistant_summary,
            selected_toolboxes=state.get("selected_toolboxes"),
            max_chars=profile.get("cloud_brief_max_chars", 8000),
        )

        if brief:
            # Anonymize the brief text as well
            if profile.get("cloud_anonymization_enabled", True):
                anon_ctx = {
                    "name": profile.get("name", ""),
                    "custom_sensitive_terms": profile.get("custom_sensitive_terms", []),
                }
                brief, brief_mapping = anonymize(brief, anon_ctx)
                if anon_mapping is not None:
                    anon_mapping.update(brief_mapping)
                else:
                    anon_mapping = brief_mapping
                anonymization_placeholders_count = (
                    len(brief_mapping) if brief_mapping else 0
                )
            else:
                anonymization_placeholders_count = (
                    len(anon_mapping) if anon_mapping else 0
                )

            cloud_brief_tokens_est = estimate_brief_tokens(brief)
            logger.info(
                "[complex] Cloud brief built — tokens_est=%d placeholders=%d",
                cloud_brief_tokens_est,
                anonymization_placeholders_count,
            )
            # Replace full trimmed messages with the compact brief
            trimmed_messages = [HumanMessage(content=brief)]
        else:
            logger.info(
                "[complex] Cloud brief empty, falling back to full trimmed messages"
            )

    # ── 9.1 continued: Determine base_url for message format decision ────
    if route == "complex-cloud":
        base_url = config.get("models.cloud.base_url", "https://api.deepseek.com/v1")
    else:
        base_url = config.get("models.small.base_url", "http://127.0.0.1:1234/v1")

    if is_local_server(base_url):
        prompt_messages = with_system_for_local_server(system, trimmed_messages)
    else:
        prompt_messages = [system, *trimmed_messages]

    # ── tools_off mode (no tools) ────────────────────────────────────────
    fallback_chain: list[dict] = []
    loop_start_time: float | None = None
    if mode == "tools_off":
        try:
            loop_start_time = asyncio.get_running_loop().time()
            if route == "complex-cloud":
                llm = await get_cloud_llm()
                model_label = "large-cloud"


            else:
                llm = await get_medium_llm("default")
                model_label = "medium-default"
            log_model_attempt(model_label, "success", reason="tools_off_direct")
        except CloudUnavailableError as e:
            logger.warning(
                "[complex] Model %s unavailable (%s), falling back to medium-default",
                route,
                e,
            )
            log_model_attempt(model_label or route, "failed", reason=str(e)[:120])
            llm = await get_medium_llm("default")
            model_label = "medium-default-fallback"
            log_model_attempt(
                model_label, "success", reason="fallback_from_unavailable"
            )

        budget = _cap_budget_to_context(
            prompt_messages,
            state.get("token_budget", max_context)
            or int(config.get("complex.default_token_budget")),
        )
        response = await llm.bind(max_tokens=budget).ainvoke(prompt_messages)
        return {
            "messages": [AIMessage(content=response.content)],
            "model_used": model_label,
            "pending_tool_calls": False,
            "security_decision": None,
            "security_reason": None,
            "api_tokens_used": None,
            "fallback_chain": fallback_chain,
            "cloud_brief_tokens_est": cloud_brief_tokens_est,
            "anonymization_placeholders_count": anonymization_placeholders_count,
        }

    # ── 9.3: Dynamic tool binding ────────────────────────────────────────
    selected_toolboxes = state.get("selected_toolboxes")
    if selected_toolboxes and "all" not in selected_toolboxes:
        tools = resolve_tools(selected_toolboxes, web_on)
    else:
        tools = list(COMPLEX_TOOLS_WITH_WEB if web_on else COMPLEX_TOOLS_NO_WEB)

    # Include previously-used tools from conversation history
    # to ensure ToolMessage references remain valid
    prev_tool_names: set[str] = set()
    for msg in thread_messages:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                prev_tool_names.add(tc.get("name", ""))

    if prev_tool_names:
        all_tools = COMPLEX_TOOLS_WITH_WEB if web_on else COMPLEX_TOOLS_NO_WEB
        for t in all_tools:
            if getattr(t, "name", "") in prev_tool_names and t not in tools:
                tools.append(t)

    # ── 9.4: Tiered fallback — model acquisition ────────────────────────
    try:
        if route == "complex-cloud":
            loop_start_time = asyncio.get_running_loop().time()
            llm = await get_cloud_llm()
            model_label = "large-cloud"
            log_model_attempt("large-cloud", "success", reason="initial_route")
        elif route == "complex-vision":
            loop_start_time = asyncio.get_running_loop().time()
            llm = await get_medium_llm("vision")
            model_label = "medium-vision"
            log_model_attempt("medium-vision", "success", reason="initial_route")
        elif route == "complex-longctx":
            loop_start_time = asyncio.get_running_loop().time()
            llm = await get_medium_llm("longctx")
            model_label = "medium-longctx"
            log_model_attempt("medium-longctx", "success", reason="initial_route")
        else:
            loop_start_time = asyncio.get_running_loop().time()
            llm = await get_medium_llm("default")
            model_label = "medium-default"
            log_model_attempt("medium-default", "success", reason="initial_route")
    except CloudUnavailableError as e:
        logger.warning(
            "[complex] Model %s unavailable (%s), falling back to medium-default",
            route,
            e,
        )
        fallback_chain.append(
            {
                "model": model_label if model_label != "medium-default" else route,
                "status": "failed",
                "reason": str(e)[:120],
                "duration_ms": 0,
            }
        )
        log_model_attempt(
            model_label if model_label != "medium-default" else route,
            "failed",
            reason=str(e)[:120],
        )
        llm = await get_medium_llm("default")
        model_label = "medium-default-fallback"
        log_model_attempt(
            "medium-default-fallback", "success", reason="fallback_from_unavailable"
        )
        fallback_chain.append(
            {
                "model": "medium-default-fallback",
                "status": "success",
                "reason": "fallback_from_unavailable",
                "duration_ms": 0,
            }
        )

    budget = _cap_budget_to_context(
        prompt_messages,
        state.get("token_budget", max_context) or int(config.get("complex.default_token_budget")),
    )
    bound_llm = llm.bind_tools(tools).bind(max_tokens=budget)
    audit_debug("agent.token", "budget_computed", token_budget=budget, route=route)

    # ── Enforce Tool Discipline ───────────────────────────────────────────
    if selected_toolboxes and any(
        t in selected_toolboxes for t in ("file_ops", "web_search", "data_viz")
    ):
        # Only inject if we aren't in a cutoff loop and haven't just finished a tool call
        if not state.get("_cutoff_pending") and not any(
            isinstance(m, ToolMessage) for m in prompt_messages[-3:]
        ):
            prompt_messages.append(
                SystemMessage(
                    content="[SYSTEM INSTRUCTION]: The user specifically requested a tool action (web search, file ops, etc.). YOU MUST EMIT A VALID JSON TOOL_CALL IN THIS TURN. Do not output prose describing your actions without actually calling the tool."
                )
            )

    # ── 9.4: Tiered fallback — LLM invocation with error handling ────────
    try:
        response = await bound_llm.ainvoke(prompt_messages)
    except Exception as e:
        error_str = str(e).lower()
        if route == "complex-cloud":
            if "429" in str(e) or "rate" in error_str:
                # Rate limit: retry after delay
                loop_start_time = asyncio.get_running_loop().time()
                await asyncio.sleep(2)
                try:
                    response = await bound_llm.ainvoke(prompt_messages)
                except Exception:
                    logger.warning(
                        "[complex] Cloud retry failed, falling back to medium-default"
                    )
                    fallback_chain.append(
                        {
                            "model": "large-cloud",
                            "status": "failed",
                            "reason": "rate_limit_retry_failed",
                            "duration_ms": max(
                                0,
                                int(
                                    (
                                        asyncio.get_running_loop().time()
                                        - loop_start_time
                                    )
                                    * 1000
                                ),
                            )
                            if loop_start_time
                            else 0,
                        }
                    )
                    llm = await get_medium_llm("default")
                    prompt_messages = with_system_for_local_server(
                        system, original_trimmed_messages
                    )
                    budget = _cap_budget_to_context(
                        prompt_messages,
                        state.get("token_budget", max_context)
                        or int(config.get("complex.default_token_budget", 4096)),
                    )
                    fb_start = asyncio.get_running_loop().time()
                    response = (
                        await llm.bind_tools(tools)
                        .bind(max_tokens=budget)
                        .ainvoke(prompt_messages)
                    )
                    model_label = "medium-default-fallback"
                    fallback_chain.append(
                        {
                            "model": "medium-default-fallback",
                            "status": "success",
                            "reason": "fallback_rate_limit",
                            "duration_ms": max(
                                0,
                                int(
                                    (asyncio.get_running_loop().time() - fb_start)
                                    * 1000
                                ),
                            ),
                        }
                    )
            elif "401" in str(e) or "403" in str(e):
                # Auth error: fall back with note
                fallback_chain.append(
                    {
                        "model": "large-cloud",
                        "status": "failed",
                        "reason": "auth_error_401_403",
                        "duration_ms": max(
                            0,
                            int(
                                (
                                    asyncio.get_running_loop().time()
                                    - (
                                        loop_start_time
                                        or asyncio.get_running_loop().time()
                                    )
                                )
                                * 1000
                            ),
                        )
                        if loop_start_time
                        else 0,
                    }
                )
                llm = await get_medium_llm("default")
                prompt_messages = with_system_for_local_server(
                    system, original_trimmed_messages
                )
                budget = _cap_budget_to_context(
                    prompt_messages,
                    state.get("token_budget", max_context)
                    or int(config.get("complex.default_token_budget")),
                )
                fb_start = asyncio.get_running_loop().time()
                response = (
                    await llm.bind_tools(tools)
                    .bind(max_tokens=budget)
                    .ainvoke(prompt_messages)
                )
                content_str = str(getattr(response, "content", "") or "").strip()
                if not content_str and not getattr(response, "tool_calls", None):
                    # Local model returned empty; synthesize a response so it's not just the warning
                    synth_response = _fallback_for_blank_response(
                        thread_messages, web_search_enabled=web_on
                    )
                    content_str = str(
                        getattr(synth_response, "content", "") or ""
                    ).strip()
                response = AIMessage(
                    content=content_str
                    + "\n\n⚠️ Note: DeepSeek API key may be invalid. Check Settings → Profile → Cloud section."
                )
                model_label = "medium-default-fallback"
                fallback_chain.append(
                    {
                        "model": "medium-default-fallback",
                        "status": "success",
                        "reason": "fallback_auth_error",
                        "duration_ms": max(
                            0,
                            int((asyncio.get_running_loop().time() - fb_start) * 1000),
                        ),
                    }
                )
            else:
                logger.warning(
                    "[complex] Cloud error (%s), falling back to medium-default", e
                )
                fallback_chain.append(
                    {
                        "model": "large-cloud",
                        "status": "failed",
                        "reason": str(e)[:120],
                        "duration_ms": max(
                            0,
                            int(
                                (
                                    asyncio.get_running_loop().time()
                                    - (
                                        loop_start_time
                                        or asyncio.get_running_loop().time()
                                    )
                                )
                                * 1000
                            ),
                        )
                        if loop_start_time
                        else 0,
                    }
                )
                llm = await get_medium_llm("default")
                prompt_messages = with_system_for_local_server(
                    system, original_trimmed_messages
                )
                budget = _cap_budget_to_context(
                    prompt_messages,
                    state.get("token_budget", max_context)
                    or int(config.get("complex.default_token_budget")),
                )
                fb_start = asyncio.get_running_loop().time()
                response = (
                    await llm.bind_tools(tools)
                    .bind(max_tokens=budget)
                    .ainvoke(prompt_messages)
                )
                model_label = "medium-default-fallback"
                fallback_chain.append(
                    {
                        "model": "medium-default-fallback",
                        "status": "success",
                        "reason": "fallback_generic_cloud_error",
                        "duration_ms": max(
                            0,
                            int((asyncio.get_running_loop().time() - fb_start) * 1000),
                        ),
                    }
                )
        elif route == "complex-vision":
            logger.warning(
                "[complex] Vision model failed (%s), falling back to medium-default", e
            )
            fallback_chain.append(
                {
                    "model": "medium-vision",
                    "status": "failed",
                    "reason": str(e)[:120],
                    "duration_ms": max(
                        0,
                        int(
                            (
                                asyncio.get_running_loop().time()
                                - (loop_start_time or asyncio.get_running_loop().time())
                            )
                            * 1000
                        ),
                    )
                    if loop_start_time
                    else 0,
                }
            )
            llm = await get_medium_llm("default")
            prompt_messages = with_system_for_local_server(system, trimmed_messages)
            budget = _cap_budget_to_context(
                prompt_messages,
                state.get("token_budget", max_context)
                or int(config.get("complex.default_token_budget")),
            )
            fb_start = asyncio.get_running_loop().time()
            response = (
                await llm.bind_tools(tools)
                .bind(max_tokens=budget)
                .ainvoke(prompt_messages)
            )
            model_label = "medium-default-fallback"
            fallback_chain.append(
                {
                    "model": "medium-default-fallback",
                    "status": "success",
                    "reason": "fallback_vision_failed",
                    "duration_ms": max(
                        0, int((asyncio.get_running_loop().time() - fb_start) * 1000)
                    ),
                }
            )
        elif route == "complex-longctx":
            # Try cloud first, then medium-default
            try:
                loop_start_time = asyncio.get_running_loop().time()
                llm = await get_cloud_llm()
                budget = _cap_budget_to_context(
                    [system, *trimmed_messages],
                    state.get("token_budget", max_context)
                    or int(config.get("complex.default_token_budget")),
                )
                response = (
                    await llm.bind_tools(tools)
                    .bind(max_tokens=budget)
                    .ainvoke([system, *trimmed_messages])
                )
                model_label = "large-cloud-fallback"
                fallback_chain.append(
                    {
                        "model": "large-cloud-fallback",
                        "status": "success",
                        "reason": "longctx_cloud_escalation",
                        "duration_ms": max(
                            0,
                            int(
                                (asyncio.get_running_loop().time() - loop_start_time)
                                * 1000
                            ),
                        ),
                    }
                )
            except Exception as e:
                import logging; logging.debug("Silent error suppressed: %s", e)
                fallback_chain.append(
                    {
                        "model": "medium-longctx",
                        "status": "failed",
                        "reason": "longctx_local_unavailable_cloud_failed",
                        "duration_ms": max(
                            0,
                            int(
                                (
                                    asyncio.get_running_loop().time()
                                    - (
                                        loop_start_time
                                        or asyncio.get_running_loop().time()
                                    )
                                )
                                * 1000
                            ),
                        )
                        if loop_start_time
                        else 0,
                    }
                )
                llm = await get_medium_llm("default")
                prompt_messages = with_system_for_local_server(system, trimmed_messages)
                budget = _cap_budget_to_context(
                    prompt_messages,
                    state.get("token_budget", max_context)
                    or int(config.get("complex.default_token_budget")),
                )
                fb_start = asyncio.get_running_loop().time()
                response = (
                    await llm.bind_tools(tools)
                    .bind(max_tokens=budget)
                    .ainvoke(prompt_messages)
                )
                model_label = "medium-default-fallback"
                fallback_chain.append(
                    {
                        "model": "medium-default-fallback",
                        "status": "success",
                        "reason": "fallback_last_resort",
                        "duration_ms": max(
                            0,
                            int((asyncio.get_running_loop().time() - fb_start) * 1000),
                        ),
                    }
                )
        else:
            # medium-default failure — produce a graceful error instead of crashing the graph
            logger.error(
                "[complex] Medium-default model failed with no fallback available: %s",
                e,
            )
            fallback_chain.append(
                {
                    "model": route,
                    "status": "failed",
                    "reason": str(e)[:120],
                    "duration_ms": max(
                        0,
                        int(
                            (
                                asyncio.get_running_loop().time()
                                - (loop_start_time or asyncio.get_running_loop().time())
                            )
                            * 1000
                        ),
                    )
                    if loop_start_time
                    else 0,
                }
            )
            return AgentState(  # type: ignore[call-arg]
                messages=[
                    AIMessage(
                        content="I encountered an error while processing your request. "
                        "The language model is currently unavailable. "
                        "Please check that LM Studio is running and try again."
                    )
                ],
                fallback_chain=fallback_chain,
            )

    # If we fell back from cloud, skip deanonymization — fallback model got non-anonymized input
    if "fallback" in model_label and anon_mapping:
        anon_mapping = None

    # ── 9.2 continued: Deanonymize response (before stripping think tags) ─
    if anon_mapping and route == "complex-cloud":
        if response.content:
            response = AIMessage(content=deanonymize(response.content, anon_mapping))
        if hasattr(response, "tool_calls") and response.tool_calls:
            for tc in response.tool_calls:
                if tc.get("args"):
                    args_str = json.dumps(tc["args"])
                    args_str = deanonymize(args_str, anon_mapping)
                    tc["args"] = json.loads(args_str)

    # ── 9.5: Cloud token usage tracking ──────────────────────────────────
    if route == "complex-cloud" and "fallback" not in model_label:
        usage = getattr(response, "response_metadata", {}).get("token_usage", {})
        if not usage:
            usage = getattr(response, "usage_metadata", {})
        if usage:
            api_tokens = {
                "prompt_tokens": usage.get("input_tokens")
                or usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("output_tokens")
                or usage.get("completion_tokens", 0),
            }

    has_tool_calls = bool(getattr(response, "tool_calls", None))
    if not has_tool_calls and not str(getattr(response, "content", "") or "").strip():
        response = _fallback_for_blank_response(
            thread_messages, web_search_enabled=web_on
        )
        has_tool_calls = bool(getattr(response, "tool_calls", None))

    out_messages: list = [response]

    # Local OpenAI-compatible servers often return plain text instead of
    # structured tool_calls. When uploads are clearly present, read the
    # files here and re-prompt once.
    if not has_tool_calls:
        utext = _latest_user_text(thread_messages)
        paths = _workspace_paths_from_text(utext)
        if (
            paths
            and _user_intent_needs_workspace_read(utext)
            and _looks_like_prose_tool_stall(response)
        ):
            bundle = await _auto_read_workspace_bundle(paths)
            if bundle.strip():
                nudge = HumanMessage(content=bundle)
                second_prompt = with_system_for_local_server(
                    system, thread_messages + [nudge]
                )
                recapped = _cap_budget_to_context(
                    second_prompt,
                    state.get("token_budget", max_context)
                    or int(config.get("complex.default_token_budget")),
                )
                llm_recapped = llm.bind_tools(tools).bind(max_tokens=recapped)
                response = await llm_recapped.ainvoke(second_prompt)
                has_tool_calls = bool(getattr(response, "tool_calls", None))
                if (
                    not has_tool_calls
                    and not str(getattr(response, "content", "") or "").strip()
                ):
                    response = _fallback_for_blank_response(
                        thread_messages + [nudge], web_search_enabled=web_on
                    )
                    has_tool_calls = bool(getattr(response, "tool_calls", None))
                out_messages = [nudge, response]

    # Strip <think> tags from all assistant responses before returning
    for i, msg in enumerate(out_messages):
        if isinstance(msg, AIMessage) and msg.content:
            cleaned = _strip_thinking_tags(msg.content)
            if cleaned != msg.content:
                out_messages[i] = AIMessage(content=cleaned)

    # ── Cutoff detection: auto-continue if LLM hit token budget ────────────
    _cutoff_round = state.get("_cutoff_round", 0)

    meta = getattr(response, "response_metadata", {})
    finish_reason = meta.get("finish_reason")
    completion_tokens = meta.get("token_usage", {}).get("completion_tokens", 0)

    is_length_cutoff = finish_reason in ("length", "max_tokens") or (
        completion_tokens > 256
        and completion_tokens
        >= (
            state.get("token_budget") or int(config.get("complex.default_token_budget"))
        )
        - 15
    )

    if (
        not has_tool_calls
        and _cutoff_round < MAX_CUTOFF_RETRIES
        and response
        and is_length_cutoff
    ):
        logger.info(
            "[complex] Response cut off (finish_reason=%s, tokens=%d), auto-continuing round %d/%d",
            finish_reason,
            completion_tokens,
            _cutoff_round + 1,
            MAX_CUTOFF_RETRIES,
        )
        return {
            "messages": out_messages,
            "model_used": model_label,
            "pending_tool_calls": False,
            "security_decision": None,
            "security_reason": None,
            "_cutoff_pending": True,
            "_cutoff_round": _cutoff_round + 1,
            "api_tokens_used": api_tokens,
            "fallback_chain": fallback_chain,
            "cloud_brief_tokens_est": cloud_brief_tokens_est,
            "anonymization_placeholders_count": anonymization_placeholders_count,
        }

    return {
        "messages": out_messages,
        "model_used": model_label,
        "pending_tool_calls": bool(getattr(response, "tool_calls", None)),
        "security_decision": None,
        "security_reason": None,
        "_cutoff_pending": False,
        "_cutoff_round": _cutoff_round,
        "api_tokens_used": api_tokens,
        "fallback_chain": fallback_chain,
        "cloud_brief_tokens_est": cloud_brief_tokens_est,
        "anonymization_placeholders_count": anonymization_placeholders_count,
    }


@log_node("tool_action")
async def complex_tool_action_node(state: AgentState) -> AgentState:
    """
    Executes already-approved tool calls and appends tool outputs to the thread.
    Truncates large tool outputs to avoid blowing the context window.
    """
    current_messages = list(state.get("messages") or [])
    if not current_messages:
        return {"pending_tool_calls": False}

    last_message = current_messages[-1]
    if not bool(getattr(last_message, "tool_calls", None)):
        return {"pending_tool_calls": False}

    web_on = state.get("web_search_enabled")
    if web_on is None:
        web_on = True
    web_on = bool(web_on)

    tools = COMPLEX_TOOLS_WITH_WEB if web_on else COMPLEX_TOOLS_NO_WEB
    tool_node = ToolNode(tools)
    tool_payload = await tool_node.ainvoke({"messages": current_messages})
    output_messages = tool_payload.get("messages", [])

    if len(output_messages) >= len(current_messages):
        delta = output_messages[len(current_messages) :]
    else:
        delta = output_messages

    # Truncate large tool outputs to stay within context window.
    _MAX_TOOL_OUTPUT_CHARS = int(config.get("tool_output.max_tool_output_chars", 20000))
    truncated_delta = []
    for msg in delta:
        if isinstance(msg, ToolMessage):
            content = (
                msg.content if isinstance(msg.content, str) else str(msg.content or "")
            )
            if len(content) > _MAX_TOOL_OUTPUT_CHARS:
                truncated = (
                    content[:_MAX_TOOL_OUTPUT_CHARS]
                    + "\n\n[... output truncated for context window. Use read_workspace_file for full content.]"
                )
                msg = ToolMessage(
                    content=truncated,
                    tool_call_id=msg.tool_call_id,
                    name=getattr(msg, "name", None),
                )
        truncated_delta.append(msg)
    delta = truncated_delta

    nudge = build_fetch_retry_nudge_messages(delta) if web_on else []
    ws_nudge = build_web_search_answer_nudge_messages(delta) if web_on else []

    # Nudge the model to retry if a tool call failed with an error
    error_nudge = []
    for msg in delta:
        if isinstance(msg, ToolMessage):
            content = (
                msg.content if isinstance(msg.content, str) else str(msg.content or "")
            )
            tool_name = getattr(msg, "name", "") or ""
            if "Error" in content and (
                "Field required" in content or "No code provided" in content
            ):
                error_nudge.append(
                    HumanMessage(
                        content=(
                            f"[Internal reminder] The tool call to **{tool_name}** failed because required parameters "
                            f"were missing. Please retry the tool call with the correct parameters. "
                            f"For notebook_run, you must provide the 'code' parameter with Python code."
                        )
                    )
                )
                break
            elif "FileNotFoundError" in content and tool_name == "notebook_run":
                error_nudge.append(
                    HumanMessage(
                        content=(
                            "[Internal reminder] notebook_run could not find the file. "
                            "Files are in the workspace directory. The variable WORKSPACE_DIR is pre-defined. "
                            'Use: pd.read_csv(f"{WORKSPACE_DIR}/filename.csv") — retry with the corrected path.'
                        )
                    )
                )
                break
            elif "ModuleNotFoundError" in content and tool_name == "notebook_run":
                import re as _re

                mod_match = _re.search(r"No module named '([^']+)'", content)
                mod_name = mod_match.group(1) if mod_match else "unknown"
                error_nudge.append(
                    HumanMessage(
                        content=(
                            f"[Internal reminder] notebook_run failed because '{mod_name}' is not installed. "
                            f"Available libraries: pandas, numpy, matplotlib, seaborn, plotly, scipy, scikit-learn, "
                            f"openpyxl, xlsxwriter, pillow, sympy, chardet, tabulate, jinja2. "
                            f"Retry using only available libraries."
                        )
                    )
                )
                break
            elif (
                "Error" in content
                and tool_name == "notebook_run"
                and "Traceback" in content
            ):
                lines = content.strip().split("\n")
                error_line = lines[-1] if lines else "Unknown error"
                error_nudge.append(
                    HumanMessage(
                        content=(
                            f"[Internal reminder] notebook_run hit a Python error: {error_line}\n"
                            f"Common fixes: convert string columns to numeric with pd.to_numeric(col, errors='coerce'), "
                            f"strip '%' from percentage strings, handle NaN values, check column dtypes with df.dtypes. "
                            f"Please fix the code and retry."
                        )
                    )
                )
                break

    if nudge or ws_nudge or error_nudge:
        delta = list(delta) + nudge + ws_nudge + error_nudge

    return {
        "messages": delta,
        "pending_tool_calls": False,
        "execution_approved": None,
    }
