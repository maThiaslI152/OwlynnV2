"""Memory inject/retrieve/write nodes for the LangGraph pipeline.

See docs/MEMORY.md. Lite inject runs before router; retrieve after router gate.

- **memory_inject_lite** (before router): Profile, persona, topics — no vector search
- **memory_retrieve** (after router): Gated Mem0/Qdrant when needed

- **memory_write_node** (runs AFTER response): Extracts topics and interests
  from the conversation turn, records the conversation summary, and saves
  enriched facts to Mem0 for future retrieval.

Memory scoping:
- Non-default projects use ``project:<id>`` as the Mem0 user ID (isolated).
- Default project uses the user's profile name or ``"owner"`` (shared global).
"""

from src.agent.core.state import AgentState
from src.memory.user_profile import get_profile
from src.memory.persona_manager import get_persona_by_id
from src.config.config_loader import config
import asyncio
import re
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

from src.config.audit_log import audit_debug, audit_info
from src.config.log_middleware import log_node

# Import enhanced personal assistant memory system
from src.memory.personal_assistant import (
    TopicExtractor,
    MemoryEnricher,
    record_conversation,
    get_memory_context_for_prompt,
)


def _get_mem0_user_id(state: dict) -> str:
    """
    Return a STABLE user identifier for Mem0.

    Memory scoping strategy:
    - Non-default project → "project:<project_id>" (isolated per project)
    - Default project     → user profile name or "owner" (shared global memory)

    This means project-specific conversations stay within that project's
    knowledge silo, while general chats share a common memory pool.
    """
    # Project-scoped isolation
    project_id = state.get("project_id")
    if project_id and project_id != "default":
        return f"project:{project_id}"

    # Global memory: use stable user identity
    try:
        profile = get_profile()
        name = (profile.get("name") or "").strip()
        if name and name.lower() != "user":
            return name
    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        pass
    return "owner"


# --- M4 OPTIMIZATION: Memory Context Cache ---
class MemoryContextCache:
    """In-memory TTL cache for formatted memory context strings.

    Avoids rebuilding the full memory context (Mem0 search + profile + topics)
    on every request within the same thread. Entries expire after 5 minutes.
    Invalidated explicitly when memory_write_node saves new facts.

    Uses a threading lock to prevent race conditions from concurrent async tasks.
    """

    _cache = {}
    _ttl_seconds = int(config.get("memory.cache.ttl", 300))  # default 5 minutes
    _lock = __import__("threading").Lock()

    @classmethod
    def get(cls, thread_id: str, project_id: str) -> tuple[str, str] | None:
        """Get cached context if still valid."""
        cache_key = f"{thread_id}:{project_id}"
        with cls._lock:
            if cache_key in cls._cache:
                cached_at, context_tuple = cls._cache[cache_key]
                age = datetime.now() - cached_at
                if age < timedelta(seconds=cls._ttl_seconds):
                    audit_debug(
                        "memory.cache",
                        "cache_hit",
                        age_seconds=int(age.total_seconds()),
                    )
                    return context_tuple
                else:
                    audit_debug(
                        "memory.cache",
                        "cache_miss",
                        reason="expired",
                        age_seconds=int(age.total_seconds()),
                    )
                    del cls._cache[cache_key]
            else:
                audit_debug("memory.cache", "cache_miss", reason="not_found")
            return None

    @classmethod
    def set(cls, thread_id: str, project_id: str, context_tuple: tuple[str, str]):
        """Cache context tuple with timestamp."""
        cache_key = f"{thread_id}:{project_id}"
        with cls._lock:
            cls._cache[cache_key] = (datetime.now(), context_tuple)

    @classmethod
    def invalidate(cls, thread_id: str):
        """Invalidate cache when memory updates."""
        with cls._lock:
            keys_to_delete = [
                k for k in cls._cache.keys() if k.startswith(f"{thread_id}:")
            ]
            for k in keys_to_delete:
                del cls._cache[k]

    @classmethod
    def invalidate_on_write(cls, thread_id: str):
        """Called by memory_write_node after saving new memories.
        Invalidates cache and signals that a WebSocket notification should be sent."""
        cls.invalidate(thread_id)
        audit_debug("memory.cache", "cache_invalidated", reason="memory_updated")
        return True

    @classmethod
    def clear_old(cls):
        """Remove expired cache entries."""
        now = datetime.now()
        with cls._lock:
            expired = [
                k
                for k, (t, _) in cls._cache.items()
                if now - t > timedelta(seconds=cls._ttl_seconds)
            ]
            for k in expired:
                del cls._cache[k]


async def _build_memory_context_async(
    thread_id: str,
    project_id: str,
    persona_id: str,
    user_message: str,
    state: dict,
    *,
    vector_search: bool = True,
) -> tuple[str, str]:
    from src.memory.long_term import memory

    mem0_uid = _get_mem0_user_id(state)

    from src.memory.educator import (
        fetch_study_struggle_memories,
        is_struggle_recall_query,
        prioritize_study_memories,
    )

    results = []
    if vector_search and memory is not None:
        try:
            results_dict = await asyncio.to_thread(
                lambda: memory.search(
                    user_message, filters={"user_id": mem0_uid}, limit=5
                )
            )
            results = (
                results_dict.get("results", [])
                if isinstance(results_dict, dict)
                else results_dict
            )
        except Exception as e:
            logger.warning("[mem0] search failed: %s", e)

        if is_struggle_recall_query(user_message):
            try:
                study_hits = await asyncio.to_thread(
                    lambda: fetch_study_struggle_memories(
                        memory, mem0_uid, user_message
                    )
                )
                if study_hits:
                    results = prioritize_study_memories([*study_hits, *results])
            except Exception as e:
                logger.warning("[mem0] study struggle search failed: %s", e)

        if project_id != "default":
            try:
                global_uid = "owner"
                try:
                    p = get_profile()
                    n = (p.get("name") or "").strip()
                    if n and n.lower() != "user":
                        global_uid = n
                except Exception as e:
                    logger.warning("Error suppressed: %s", e)
                    pass
                global_dict = await asyncio.to_thread(
                    lambda: memory.search(
                        user_message, filters={"user_id": global_uid}, limit=3
                    )
                )
                global_results = (
                    global_dict.get("results", [])
                    if isinstance(global_dict, dict)
                    else global_dict
                )
                results.extend(global_results)
            except Exception as e:
                logger.warning("[mem0] global search failed: %s", e)

    profile = get_profile()
    enhanced_context = await get_memory_context_for_prompt()

    project_instructions = ""
    if project_id and project_id != "default":
        try:
            from src.memory.project import project_manager

            project = await project_manager.get_project(project_id)
            if project:
                parts = []
                if project.get("instructions"):
                    parts.append(project["instructions"])
                if project.get("name"):
                    parts.insert(0, f"Active project: {project['name']}")
                file_count = len(project.get("files", []))
                if file_count:
                    parts.append(
                        f"This project has {file_count} knowledge file(s) indexed."
                    )
                project_instructions = "\n".join(parts)
        except Exception as e:
            logger.warning("[project] instructions fetch failed: %s", e)

    knowledge_facts = []
    standard_results = []

    ninety_days_ago = datetime.now() - timedelta(days=90)

    for item in results:
        if isinstance(item, dict):
            meta = item.get("metadata") or {}
            if meta.get("type") == "knowledge_cache":
                fact_text = item.get("memory") or item.get("text", "")
                timestamp_str = meta.get("timestamp")
                if timestamp_str:
                    try:
                        ts = datetime.fromisoformat(timestamp_str)
                        if ts < ninety_days_ago:
                            fact_text += " [Note: This fact is >3 months old, consider verifying if it's a fast-moving topic]"
                    except ValueError:
                        pass
                knowledge_facts.append(fact_text)
            else:
                standard_results.append(item)
        else:
            standard_results.append(item)

    memory_context = format_memory_context(
        standard_results, profile, enhanced_context, project_instructions
    )
    knowledge_context = (
        "\n".join(f"- {f}" for f in knowledge_facts) if knowledge_facts else ""
    )

    return memory_context, knowledge_context


async def background_prefetch_memory(
    thread_id: str, project_id: str, persona_id: str, user_message: str
) -> None:
    """Pre-fetch memory context and cache it in the background."""
    cached_tuple = MemoryContextCache.get(thread_id, project_id)
    if cached_tuple:
        return

    state_mock = {"project_id": project_id}
    memory_context, knowledge_context = await _build_memory_context_async(
        thread_id, project_id, persona_id, user_message, state_mock
    )

    MemoryContextCache.set(thread_id, project_id, (memory_context, knowledge_context))
    audit_info(
        "memory.prefetch", "context_prefetched", context_chars=len(memory_context)
    )


def _persona_summary(persona_id: str) -> str:
    persona = get_persona_by_id(persona_id)
    return (
        f"You are {persona['name']}, a {persona['role']}. "
        f"Tone: {persona['tone']}. {persona['instructions']}"
    )


def _last_user_message_content(state: AgentState) -> str:
    messages = state.get("messages") or []
    if not messages:
        return ""
    raw = messages[-1].content
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        parts = []
        for block in raw:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "\n".join(parts)
    return str(raw)


@log_node("memory_inject_lite")
async def memory_inject_lite_node(state: AgentState) -> AgentState:
    """Fast pre-router inject: profile, persona, topics — no vector search.

    Pentest mode: bypasses global memory entirely, injects engagement context.
    """
    import time

    thread_id = state.get("thread_id", "default")
    user_message = _last_user_message_content(state)
    project_id = state.get("project_id") or "default"
    persona_id = state.get("persona_id") or "default"
    scenario_id = state.get("scenario_id")

    # Pentest mode: engagement-scoped context, no global memory
    if scenario_id == "pentest":
        from src.memory.pentest_engagement import (
            get_active_engagement,
            get_engagement_context,
        )

        eng = get_active_engagement()
        if eng:
            memory_context = get_engagement_context(eng["id"])
        else:
            memory_context = (
                "No active engagement. Use engagement_create to start a new pentest."
            )
        profile = get_profile()
        name = (profile.get("name") or "").strip()
        persona_str = (
            f"You are a penetration testing assistant. "
            f"Be concise and technical. User: {name or 'operator'}."
        )
        audit_info(
            "memory.inject",
            "pentest_context_injected",
            context_chars=len(memory_context),
            engagement=eng["id"] if eng else None,
        )
        return {
            "memory_context": memory_context,
            "knowledge_context": "",
            "persona": persona_str,
            "turn_start_time": time.time(),
        }

    # Normal/study mode: global memory
    memory_context, _knowledge = await _build_memory_context_async(
        thread_id,
        project_id,
        persona_id,
        user_message,
        state,
        vector_search=False,
    )
    audit_info(
        "memory.inject",
        "lite_context_assembled",
        context_chars=len(memory_context),
    )
    return {
        "memory_context": memory_context,
        "knowledge_context": "",
        "persona": _persona_summary(persona_id),
        "turn_start_time": time.time(),
    }


@log_node("memory_retrieve")
async def memory_retrieve_node(state: AgentState) -> AgentState:
    """Post-router vector retrieval and scenario markdown (gated).

    Pentest mode: skips global Mem0/Qdrant entirely, returns engagement context.
    """
    from src.memory.scenarios import format_scenario_context

    thread_id = state.get("thread_id", "default")
    project_id = state.get("project_id") or "default"
    persona_id = state.get("persona_id") or "default"
    user_message = _last_user_message_content(state)
    scenario_id = state.get("scenario_id")
    scenario_block = format_scenario_context(scenario_id)

    # Pentest mode: engagement-scoped retrieval, no global memory
    if scenario_id == "pentest":
        from src.memory.pentest_engagement import (
            get_active_engagement,
            get_engagement_context,
            get_findings_summary,
        )

        eng = get_active_engagement()
        if eng:
            engagement_context = get_engagement_context(eng["id"])
            f_summary = get_findings_summary(eng["id"])
            # Include playbook + constraints alongside engagement context
            merged = engagement_context
            if scenario_block:
                merged = f"{merged}\n\n{scenario_block}".strip()
            # Inject finding details for the agent to reference
            if f_summary["total"] > 0:
                from src.memory.pentest_engagement import list_findings

                findings = list_findings(eng["id"])
                finding_lines = []
                for f in findings[:20]:  # Cap at 20 findings
                    sev = f.get("severity", "info").upper()
                    title = f.get("title", "Untitled")
                    fid = f.get("id", "?")
                    status = f.get("status", "unknown")
                    finding_lines.append(f"  [{sev}] {fid}: {title} ({status})")
                merged = f"{merged}\n\n### Current Findings\n" + "\n".join(
                    finding_lines
                )
        else:
            merged = (
                "No active engagement. Use engagement_create to start a new pentest."
            )
            if scenario_block:
                merged = f"{merged}\n\n{scenario_block}".strip()

        audit_info(
            "memory.retrieve",
            "pentest_engagement_context",
            context_chars=len(merged),
            engagement=eng["id"] if eng else None,
        )
        return {
            "memory_context": merged,
            "knowledge_context": "",
            "scenario_context": scenario_block or None,
        }

    # Normal/study mode: global memory retrieval
    needs = state.get("needs_memory_retrieval")
    if needs is None:
        route = state.get("route") or ""
        needs = route.startswith("complex")

    from src.memory.educator import (
        fetch_study_struggle_memories,
        format_struggle_recall_block,
        is_struggle_recall_query,
    )

    if is_struggle_recall_query(user_message):
        needs = True
        if not scenario_id:
            scenario_id = "study"

    base_context = state.get("memory_context") or ""
    knowledge_context = state.get("knowledge_context") or ""

    if needs:
        cached_tuple = MemoryContextCache.get(thread_id, project_id)
        if cached_tuple:
            base_context, knowledge_context = cached_tuple
            audit_debug("memory.retrieve", "cache_hit", context_chars=len(base_context))
        else:
            full_context, knowledge_context = await _build_memory_context_async(
                thread_id,
                project_id,
                persona_id,
                user_message,
                state,
                vector_search=True,
            )
            base_context = full_context
            MemoryContextCache.set(
                thread_id, project_id, (base_context, knowledge_context)
            )
            audit_info(
                "memory.retrieve",
                "vector_context_assembled",
                context_chars=len(base_context),
                knowledge_chars=len(knowledge_context),
            )

    merged_context = base_context
    if scenario_block:
        merged_context = f"{merged_context}\n\n{scenario_block}".strip()

    struggle_block = ""
    if is_struggle_recall_query(user_message):
        from src.memory.long_term import memory as mem0_memory

        mem0_uid = _get_mem0_user_id(state)
        if mem0_memory is not None:
            try:
                study_hits = await asyncio.to_thread(
                    lambda: fetch_study_struggle_memories(
                        mem0_memory, mem0_uid, user_message
                    )
                )
                struggle_block = format_struggle_recall_block(study_hits)
            except Exception as e:
                logger.warning("[mem0] struggle recall block failed: %s", e)
        if struggle_block:
            merged_context = f"{struggle_block}\n\n{merged_context}".strip()

    out: dict = {
        "memory_context": merged_context,
        "knowledge_context": knowledge_context,
        "scenario_context": scenario_block or None,
    }
    if is_struggle_recall_query(user_message):
        out["needs_memory_retrieval"] = True
        if scenario_id:
            out["scenario_id"] = scenario_id
    return out


@log_node("memory_inject")
async def memory_inject_node(state: AgentState) -> AgentState:
    """Full inject (lite + vector) — used in tests and legacy callers."""
    lite = await memory_inject_lite_node(state)
    merged = {**state, **lite, "needs_memory_retrieval": True}
    retrieved = await memory_retrieve_node(merged)
    return {**lite, **retrieved}


def format_memory_context(
    results: list,
    profile: dict,
    enhanced_context: str = "",
    project_instructions: str = "",
) -> str:
    """Format memory context with profile, relevant memories, enriched personal knowledge, and project instructions."""
    lines = []

    # Add project instructions first (highest priority — shapes all responses)
    if project_instructions:
        lines.append(
            "=== ACTIVE PROJECT CONTEXT (follow these instructions closely) ==="
        )
        lines.append(project_instructions)
        lines.append("=== END PROJECT CONTEXT ===")

    # Add enhanced memory context (topics, interests, recent convos) — capped to stay within model context
    if enhanced_context:
        lines.append("\n=== Your Knowledge About User ===")
        max_enhanced_chars = (
            24000  # ~6000 tokens — leave room for system prompt + messages
        )
        if len(enhanced_context) > max_enhanced_chars:
            enhanced_context = (
                enhanced_context[:max_enhanced_chars]
                + "\n... [truncated for context budget]"
            )
        lines.append(enhanced_context)

    # Add user profile (only human-relevant fields, not config)
    _PROFILE_SKIP = {
        "system_prompt",
        "custom_instructions",
        "llm_base_url",
        "llm_model_name",
        "small_llm_base_url",
        "small_llm_model_name",
        "large_llm_base_url",
        "large_llm_model_name",
        "temperature",
        "top_p",
        "max_tokens",
        "top_k",
        "streaming_enabled",
        "show_thinking",
        "show_tool_execution",
        "lm_studio_fold_system",
        "short_term_enabled",
        "long_term_enabled",
        "domains_of_interest",
    }
    if profile:
        lines.append("\n=== User Profile ===")
        for k, v in profile.items():
            if v and k not in _PROFILE_SKIP:
                lines.append(f"  {k}: {v}")

    # Add relevant past context
    if results:
        from src.memory.educator import is_study_memory_item

        study_items = [r for r in results if is_study_memory_item(r)]
        other_items = [r for r in results if not is_study_memory_item(r)]
        if study_items:
            lines.append("\n=== Prior Study Struggles & Mastery (cite when asked) ===")
            for item in study_items:
                if isinstance(item, dict):
                    lines.append(f"  - {item.get('memory', item)}")
                else:
                    lines.append(f"  - {item}")
        if other_items:
            lines.append("\n=== Relevant Past Context ===")
            for item in other_items:
                if isinstance(item, dict):
                    lines.append(f"  - {item.get('memory', item)}")
                else:
                    lines.append(f"  - {item}")

    final_text = "\n".join(lines) if lines else "No prior memory available."
    if len(final_text) > 12000:
        final_text = final_text[:12000] + "\n... [truncated for context budget]"
    return final_text


# --- WRITE: fires after response is generated ---
async def _should_save_memory(last_human: str, last_ai: str) -> bool:
    """Selective memory gate: only save if the conversation has meaningful content.

    Skips:
    - Very short or empty messages
    - Purely casual/greeting exchanges
    - Messages where the AI response is just a confirmation/hand-off
    """
    # Handle multimodal content (list of dicts with text/image parts)
    if isinstance(last_human, list):
        human_stripped = " ".join(
            p.get("text", "") for p in last_human if isinstance(p, dict)
        ).strip()
    else:
        human_stripped = str(last_human).strip()
    ai_stripped = str(last_ai).strip()

    # Skip empty
    if not human_stripped or not ai_stripped:
        return False

    # Skip very short messages (< 10 chars)
    if len(human_stripped) < 10 and len(ai_stripped) < 10:
        return False

    # Skip common greeting patterns (align with router keyword_bypass)
    _greeting_re = re.compile(
        r"\b(hello|hi|hey|thanks|thank you|bye|goodbye)\b", re.IGNORECASE
    )
    if _greeting_re.search(human_stripped) and len(human_stripped) < 40:
        return False
    greeting_patterns = {
        "hello",
        "hi",
        "hey",
        "thanks",
        "thank you",
        "ok",
        "okay",
        "goodbye",
        "bye",
    }
    human_lower = human_stripped.lower().rstrip(".!?")
    if human_lower in greeting_patterns:
        return False

    # Skip if AI response is very short and appears to be a simple acknowledgment
    ai_lower = ai_stripped.lower()
    simple_acknowledgments = {
        "you're welcome",
        "you are welcome",
        "no problem",
        "happy to help",
        "glad to help",
        "anytime",
        "sure",
        "okay",
        "done",
        "got it",
    }
    if ai_stripped.strip(".! ").lower() in simple_acknowledgments:
        return False

    return True


async def _is_semantically_similar(memory, new_text: str, user_id: str) -> bool:
    """Check if a semantically similar memory already exists to avoid duplicates."""
    from src.memory.long_term import memory as mem0_memory

    if mem0_memory is None:
        return False
    try:
        results_dict = await asyncio.to_thread(
            lambda: mem0_memory.search(
                new_text[:200], filters={"user_id": user_id}, limit=3
            ),
        )
        results = (
            results_dict.get("results", [])
            if isinstance(results_dict, dict)
            else results_dict
        )
        for item in results:
            if isinstance(item, dict):
                existing = (item.get("memory") or item.get("text", "")).lower().strip()
                new_lower = new_text.lower().strip()
                # If the new text is a substring of existing or vice versa, skip
                if existing and (existing in new_lower or new_lower in existing):
                    return True
    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        pass
    return False


async def _evaluate_and_cache_knowledge(
    messages: list, mem0_uid: str, memory_store
) -> None:
    """Evaluates if a web search was performed and extracts synthesized knowledge."""
    # Check if web_search was used in the current turn
    web_search_used = any(
        hasattr(m, "name") and m.name == "web_search" and m.type == "tool"
        for m in messages
    )
    if not web_search_used:
        return

    # Extract human and AI messages
    last_human = next(
        (
            m.content
            for m in reversed(messages)
            if hasattr(m, "type") and m.type == "human"
        ),
        "",
    )
    last_ai = next(
        (
            m.content
            for m in reversed(messages)
            if hasattr(m, "type") and m.type == "ai"
        ),
        "",
    )

    if not last_human or not last_ai:
        return

    try:
        from src.agent.llm import get_small_llm
        from langchain_core.messages import HumanMessage

        small_llm = await get_small_llm()
        evaluator_prompt = f"""Evaluate the following web search interaction:
User asked: {last_human}
AI answered: {last_ai}

Was this search about technical documentation, new coding patterns, definitions, or tool updates? Or was it ephemeral data (weather, stock, daily news)?
If it is ephemeral data, reply with exactly: DISCARD
If it is valuable technical knowledge to keep, reply with a concise synthesized summary of the new facts learned (1-2 sentences max). Do NOT include preamble.

Response:"""

        response = await small_llm.ainvoke([HumanMessage(content=evaluator_prompt)])
        content = response.content.strip()

        if content and not content.upper().startswith("DISCARD"):
            # Save the synthesized fact to Mem0 with metadata
            await asyncio.to_thread(
                memory_store.add,
                content,
                user_id=mem0_uid,
                metadata={
                    "type": "knowledge_cache",
                    "timestamp": datetime.now().isoformat(),
                },
                infer=False,
            )
            audit_info("memory.knowledge_cache", "fact_saved", fact_chars=len(content))
    except Exception as e:
        logger.warning("[KnowledgeCache] Evaluation failed: %s", e)


@log_node("memory_write")
async def memory_write_node(state: AgentState) -> AgentState:
    """Post-reasoning node: extract and persist memories from the conversation turn.

    Steps:
    1. Selective memory gate: skip trivial/greeting exchanges
    2. Dedup check: skip semantically similar memories
    3. Record conversation summary (topics, interests, key questions)
    4. Extract topics and interests via regex patterns
    5. Save enriched fact to Mem0 with stable user ID
    6. Invalidate memory context cache so next request gets fresh data
    7. Set ``memory_invalidated=True`` to trigger WebSocket notification

    Pentest mode: skips all global memory writes, logs to engagement timeline.
    """
    thread_id = state.get("thread_id", "default")
    messages = state.get("messages", [])
    session_id = state.get("session_id", thread_id)
    scenario_id = state.get("scenario_id")

    if not messages:
        return {}

    # Extract last human and AI messages
    last_human = next(
        (
            m.content
            for m in reversed(messages)
            if hasattr(m, "type") and m.type == "human"
        ),
        None,
    )
    last_ai = next(
        (
            m.content
            for m in reversed(messages)
            if hasattr(m, "type") and m.type == "ai"
        ),
        None,
    )

    if not (last_human and last_ai):
        return {}

    # Pentest mode: skip global memory, log to engagement timeline
    if scenario_id == "pentest":
        if not await _should_save_memory(last_human, last_ai):
            return {}
        try:
            from src.memory.pentest_engagement import (
                get_active_engagement,
                log_event,
            )

            eng = get_active_engagement()
            if eng:
                human_preview = str(last_human)[:200]
                await log_event(
                    eng["id"],
                    "conversation_turn",
                    f"User: {human_preview}...",
                    phase=eng.get("phase"),
                )
                audit_info(
                    "memory.write",
                    "pentest_timeline_logged",
                    engagement=eng["id"],
                )
        except Exception as e:
            logger.warning("[Memory] Failed to log pentest timeline: %s", e)
        return {"memory_invalidated": True}

    # --- Selective memory gate ---
    if not await _should_save_memory(last_human, last_ai):
        logger.debug(
            "[Memory] Skipping memory save (gate rejected trivial/greeting exchange)"
        )
        audit_debug(
            "memory.write",
            "gate_skipped",
            reason="greeting_or_trivial",
            human_len=len(str(last_human)),
            ai_len=len(str(last_ai)),
        )
        return {}

    # Record this turn in conversation
    try:
        # Convert messages to dict format
        message_dicts = []
        for msg in messages:
            if hasattr(msg, "type"):
                role = "user" if msg.type == "human" else "assistant"
            else:
                role = msg.get("role", "user")

            content = msg.content if hasattr(msg, "content") else msg.get("content", "")
            # Flatten multimodal content (list of text/image blocks) to text only
            if isinstance(content, list):
                content = " ".join(
                    p.get("text", "") if isinstance(p, dict) else str(p)
                    for p in content
                )
            message_dicts.append({"role": role, "content": content})

        # Record conversation and extract topics/interests
        await record_conversation(message_dicts, session_id)

    except Exception as e:
        logger.warning("[Memory] Failed to record conversation: %s", e)

    # Save enriched facts to long-term memory
    from src.memory.long_term import memory
    from src.memory.educator import (
        build_mastery_atom,
        build_misconception_atom,
        is_study_correction,
        is_study_mastery,
        resolve_study_scenario,
    )

    mem0_uid = _get_mem0_user_id(state)
    response_style = state.get("response_style")
    human_text = str(last_human)
    ai_text = str(last_ai)
    study_scenario = resolve_study_scenario(response_style, human_text)
    extraction_scenario = "study" if study_scenario else state.get("scenario_id")

    if memory is not None:
        try:
            # Synchronous study atoms — available before async extraction completes
            if study_scenario:
                if is_study_correction(human_text):
                    atom_text = build_misconception_atom(human_text, ai_text)
                    from src.agent.pii_scrubber import scrub_for_storage

                    scrubbed_atom, _ = scrub_for_storage(atom_text)
                    await asyncio.to_thread(
                        memory.add,
                        scrubbed_atom,
                        user_id=mem0_uid,
                        metadata={
                            "type": "study_atom",
                            "tags": ["study", "misconception"],
                            "scenario_id": "study",
                        },
                        infer=False,
                    )
                    audit_info(
                        "memory.write",
                        "study_misconception_saved",
                        user_id=mem0_uid,
                    )
                elif is_study_mastery(human_text):
                    atom_text = build_mastery_atom(human_text)
                    from src.agent.pii_scrubber import scrub_for_storage

                    scrubbed_atom, _ = scrub_for_storage(atom_text)
                    await asyncio.to_thread(
                        memory.add,
                        scrubbed_atom,
                        user_id=mem0_uid,
                        metadata={
                            "type": "study_atom",
                            "tags": ["study", "mastery"],
                            "scenario_id": "study",
                        },
                        infer=False,
                    )
                    audit_info(
                        "memory.write",
                        "study_mastery_saved",
                        user_id=mem0_uid,
                    )

            # Extract topics and interests from the conversation
            conversation_text = f"{last_human} {last_ai}"
            topics = TopicExtractor.extract_topics(conversation_text)
            interests = TopicExtractor.extract_interests(conversation_text)

            # Tag with model that generated the response
            model_generated_by = (
                state.get("model_generated_by") or state.get("model_used") or "unknown"
            )
            if state.get("cloud_fallback_used"):
                fact_text = f"User asked: {last_human}. AI answered: {last_ai} [generated_by:{model_generated_by}]"
            else:
                fact_text = f"User asked: {last_human}. AI answered: {last_ai}"
            from src.agent.pii_scrubber import scrub_for_memory_write
            from src.memory.extraction import queue as extraction_queue

            scrubbed, redactions, injection_neutralized = scrub_for_memory_write(
                fact_text
            )
            if injection_neutralized:
                logger.warning(
                    "[memory] Prompt injection patterns neutralized in memory write"
                )
            queued = await extraction_queue.enqueue_extraction(
                {
                    "turn_text": scrubbed,
                    "mem0_uid": mem0_uid,
                    "project_id": state.get("project_id") or "default",
                    "scenario_id": extraction_scenario,
                    "thread_id": thread_id,
                }
            )
            audit_info(
                "memory.write",
                "extract_queued",
                user_id=mem0_uid,
                queued=queued,
                redactions=redactions,
                topic_count=len(topics),
            )

            # Invalidate memory context cache since memory was updated (M4 optimization)
            # Uses invalidate_on_write to signal WebSocket forwarder
            MemoryContextCache.invalidate_on_write(thread_id)
            from src.agent.cloud.cloud_payload import (
                invalidate_brief_cache,
            )

            invalidate_brief_cache()

        except Exception as e:
            logger.warning("[Memory] Failed to save enriched memory: %s", e)

        # Knowledge Cache evaluation (runs concurrently or sequentially here)
        await _evaluate_and_cache_knowledge(messages, mem0_uid, memory)

    return {"memory_invalidated": True}
