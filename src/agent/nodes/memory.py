"""
Memory Nodes — Inject and Write Long-Term Context
===================================================

Two LangGraph nodes that bookend the reasoning pipeline:

- **memory_inject_node** (runs BEFORE router): Retrieves relevant memories
  from Mem0/Qdrant, user profile, persona, project instructions, and
  enhanced topic/interest context. Caches results for 5 minutes (M4 optimization).

- **memory_write_node** (runs AFTER response): Extracts topics and interests
  from the conversation turn, records the conversation summary, and saves
  enriched facts to Mem0 for future retrieval.

Memory scoping:
- Non-default projects use ``project:<id>`` as the Mem0 user ID (isolated).
- Default project uses the user's profile name or ``"owner"`` (shared global).
"""

from langchain_core.messages import AIMessage
from src.agent.state import AgentState
from src.memory.memory_manager import save_memory, search_memories
from src.memory.user_profile import get_profile
from src.memory.persona_manager import get_persona_by_id
from src.config.config_loader import config
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

from src.config.audit_log import audit_debug, audit_info, audit_event
from src.config.log_middleware import log_node

# Import enhanced personal assistant memory system
from src.memory.personal_assistant import (
    TopicExtractor, ConversationSummary, MemoryEnricher,
    record_conversation, get_memory_context_for_prompt,
    get_relevant_topics, get_user_interests_summary
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
    except Exception:
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
    def get(cls, thread_id: str) -> Optional[str]:
        """Get cached context if still valid."""
        with cls._lock:
            if thread_id in cls._cache:
                cached_at, context = cls._cache[thread_id]
                age = datetime.now() - cached_at
                if age < timedelta(seconds=cls._ttl_seconds):
                    audit_debug("memory.cache", "cache_hit", age_seconds=int(age.total_seconds()))
                    return context
                else:
                    audit_debug("memory.cache", "cache_miss", reason="expired", age_seconds=int(age.total_seconds()))
                    del cls._cache[thread_id]
            else:
                audit_debug("memory.cache", "cache_miss", reason="not_found")
            return None
    
    @classmethod
    def set(cls, thread_id: str, context: str):
        """Cache context with timestamp."""
        with cls._lock:
            cls._cache[thread_id] = (datetime.now(), context)
    
    @classmethod
    def invalidate(cls, thread_id: str):
        """Invalidate cache when memory updates."""
        with cls._lock:
            if thread_id in cls._cache:
                del cls._cache[thread_id]
    
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
            expired = [k for k, (t, _) in cls._cache.items() 
                       if now - t > timedelta(seconds=cls._ttl_seconds)]
            for k in expired:
                del cls._cache[k]

# --- READ: fires before the brain node ---
@log_node("memory_inject")
async def memory_inject_node(state: AgentState) -> AgentState:
    """Pre-reasoning node: build memory context for the LLM system prompt.

    Retrieves and merges:
    1. Project-scoped Mem0 memories (semantic search on last user message)
    2. Global user memories (if in a non-default project)
    3. User profile fields
    4. Persona summary
    5. Enhanced topic/interest context with time decay
    6. Active project instructions (highest priority)

    Returns state updates: ``memory_context`` and ``persona``.
    """
    thread_id    = state.get("thread_id", "default")
    user_message = state["messages"][-1].content if state.get("messages") else ""
    
    # Check cache first (M4 optimization - avoid rebuilding context repeatedly)
    cached_context = MemoryContextCache.get(thread_id)
    if cached_context:
        persona_id = state.get("persona_id") or "default"
        persona = get_persona_by_id(persona_id)
        persona_summary = f"You are {persona['name']}, a {persona['role']}. Tone: {persona['tone']}. {persona['instructions']}"
        audit_debug("memory.inject", "context_from_cache", context_chars=len(cached_context))
        return {
            "memory_context": cached_context,
            "persona": persona_summary
        }
    
    # Semantic search against long-term memory.
    # Strategy: always search project-scoped memories, and also pull global
    # user memories so the assistant still knows who you are.
    from src.memory.long_term import memory
    mem0_uid = _get_mem0_user_id(state)
    project_id = state.get("project_id") or "default"
    
    results = []
    if memory is not None:
        # 1. Project-scoped memories (or global if default project)
        try:
            results_dict = await asyncio.to_thread(lambda: memory.search(user_message, filters={"user_id": mem0_uid}, limit=5))
            results = results_dict.get("results", []) if isinstance(results_dict, dict) else results_dict
        except Exception as e:
            logger.warning("[mem0] search failed: %s", e)

        # 2. If in a non-default project, also pull global user memories
        #    so the assistant retains general knowledge about the user.
        if project_id != "default":
            try:
                global_uid = "owner"
                try:
                    p = get_profile()
                    n = (p.get("name") or "").strip()
                    if n and n.lower() != "user":
                        global_uid = n
                except Exception:
                    pass
                global_dict = await asyncio.to_thread(lambda: memory.search(user_message, filters={"user_id": global_uid}, limit=3))
                global_results = global_dict.get("results", []) if isinstance(global_dict, dict) else global_dict
                results.extend(global_results)
            except Exception as e:
                logger.warning("[mem0] global search failed: %s", e)

    # Pull structured user profile
    profile = get_profile()

    # Pull persona summary
    persona_id = state.get("persona_id") or "default"
    persona = get_persona_by_id(persona_id)
    
    # Get enhanced memory context with topics and interests
    enhanced_context = get_memory_context_for_prompt()

    # Get active project instructions (if in a project context)
    project_instructions = ""
    project_id = state.get("project_id")
    if project_id and project_id != "default":
        try:
            from src.memory.project import project_manager
            project = project_manager.get_project(project_id)
            if project:
                parts = []
                if project.get("instructions"):
                    parts.append(project["instructions"])
                # Include project name for context awareness
                if project.get("name"):
                    parts.insert(0, f"Active project: {project['name']}")
                # Include file count so the assistant knows what's available
                file_count = len(project.get("files", []))
                if file_count:
                    parts.append(f"This project has {file_count} knowledge file(s) indexed.")
                project_instructions = "\n".join(parts)
        except Exception as e:
            logger.warning("[project] instructions fetch failed: %s", e)

    # Format into a clean context block
    memory_context = format_memory_context(results, profile, enhanced_context, project_instructions)
    
    # Cache for subsequent requests (M4 optimization)
    MemoryContextCache.set(thread_id, memory_context)
    audit_info("memory.inject", "context_assembled", context_chars=len(memory_context), result_count=len(results))
    
    persona_summary = f"You are {persona['name']}, a {persona['role']}. Tone: {persona['tone']}. {persona['instructions']}"
    return {
        "memory_context": memory_context,
        "persona": persona_summary
    }

def format_memory_context(results: list, profile: dict, enhanced_context: str = "", project_instructions: str = "") -> str:
    """Format memory context with profile, relevant memories, enriched personal knowledge, and project instructions."""
    lines = []

    # Add project instructions first (highest priority — shapes all responses)
    if project_instructions:
        lines.append("=== ACTIVE PROJECT CONTEXT (follow these instructions closely) ===")
        lines.append(project_instructions)
        lines.append("=== END PROJECT CONTEXT ===")
    
    # Add enhanced memory context (topics, interests, recent convos) — capped to stay within model context
    if enhanced_context:
        lines.append("\n=== Your Knowledge About User ===")
        max_enhanced_chars = 6000  # ~1500 tokens — leave room for system prompt + messages
        if len(enhanced_context) > max_enhanced_chars:
            enhanced_context = enhanced_context[:max_enhanced_chars] + "\n... [truncated for context budget]"
        lines.append(enhanced_context)
    
    # Add user profile (only human-relevant fields, not config)
    _PROFILE_SKIP = {
        'system_prompt', 'custom_instructions', 'llm_base_url', 'llm_model_name',
        'small_llm_base_url', 'small_llm_model_name', 'large_llm_base_url', 'large_llm_model_name',
        'temperature', 'top_p', 'max_tokens', 'top_k', 'streaming_enabled',
        'show_thinking', 'show_tool_execution', 'lm_studio_fold_system',
        'short_term_enabled', 'long_term_enabled', 'domains_of_interest',
    }
    if profile:
         lines.append("\n=== User Profile ===")
         for k, v in profile.items():
              if v and k not in _PROFILE_SKIP:
                  lines.append(f"  {k}: {v}")
    
    # Add relevant past context
    if results:
         lines.append("\n=== Relevant Past Context ===")
         for item in results:
              if isinstance(item, dict):
                  lines.append(f"  - {item.get('memory', item)}")
              else:
                   lines.append(f"  - {item}")
    
    return "\n".join(lines) if lines else "No prior memory available."

# --- WRITE: fires after response is generated ---
async def _should_save_memory(last_human: str, last_ai: str) -> bool:
    """Selective memory gate: only save if the conversation has meaningful content.
    
    Skips:
    - Very short or empty messages
    - Purely casual/greeting exchanges  
    - Messages where the AI response is just a confirmation/hand-off
    """
    human_stripped = last_human.strip()
    ai_stripped = last_ai.strip()
    
    # Skip empty
    if not human_stripped or not ai_stripped:
        return False
    
    # Skip very short messages (< 10 chars)
    if len(human_stripped) < 10 and len(ai_stripped) < 10:
        return False
    
    # Skip common greeting patterns
    greeting_patterns = {"hello", "hi", "hey", "thanks", "thank you", "ok", "okay", "goodbye", "bye"}
    human_lower = human_stripped.lower().rstrip(".!?")
    if human_lower in greeting_patterns:
        return False
    
    # Skip if AI response is very short and appears to be a simple acknowledgment
    ai_lower = ai_stripped.lower()
    simple_acknowledgments = {"you're welcome", "you are welcome", "no problem", "happy to help",
                               "glad to help", "anytime", "sure", "okay", "done", "got it"}
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
            lambda: mem0_memory.search(new_text[:200], filters={"user_id": user_id}, limit=3),
        )
        results = results_dict.get("results", []) if isinstance(results_dict, dict) else results_dict
        for item in results:
            if isinstance(item, dict):
                existing = (item.get("memory") or item.get("text", "")).lower().strip()
                new_lower = new_text.lower().strip()
                # If the new text is a substring of existing or vice versa, skip
                if existing and (existing in new_lower or new_lower in existing):
                    return True
    except Exception:
        pass
    return False


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
    """
    thread_id = state.get("thread_id", "default")
    messages  = state.get("messages", [])
    session_id = state.get("session_id", thread_id)
    
    if not messages:
        return {}
    
    # Extract last human and AI messages
    last_human = next(
        (m.content for m in reversed(messages) if hasattr(m, "type") and m.type == "human"), None
    )
    last_ai = next(
        (m.content for m in reversed(messages) if hasattr(m, "type") and m.type == "ai"), None
    )
    
    if not (last_human and last_ai):
        return {}
    
    # --- Selective memory gate ---
    if not await _should_save_memory(last_human, last_ai):
        logger.debug("[Memory] Skipping memory save (gate rejected trivial/greeting exchange)")
        audit_debug("memory.write", "gate_skipped", reason="greeting_or_trivial",
                     human_len=len(str(last_human)), ai_len=len(str(last_ai)))
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
            message_dicts.append({"role": role, "content": content})
        
        # Record conversation and extract topics/interests
        await asyncio.to_thread(record_conversation, message_dicts, session_id)
        
    except Exception as e:
        logger.warning("[Memory] Failed to record conversation: %s", e)
    
    # Save enriched facts to long-term memory
    from src.memory.long_term import memory
    mem0_uid = _get_mem0_user_id(state)
    if memory is not None:
        try:
            # Extract topics and interests from the conversation
            conversation_text = f"{last_human} {last_ai}"
            topics = TopicExtractor.extract_topics(conversation_text)
            interests = TopicExtractor.extract_interests(conversation_text)
            
            # Create enriched fact
            fact_text = f"User asked: {last_human}. AI answered: {last_ai}"
            enriched_fact = MemoryEnricher.enrich_memory(fact_text, topics, interests)
            
            # --- Dedup check ---
            # Only use the fact_text for dedup (not the enriched version which includes topics)
            is_dup = await _is_semantically_similar(memory, fact_text, mem0_uid)
            if is_dup:
                logger.debug("[Memory] Skipping memory save (semantically similar exists)")
                audit_debug("memory.write", "dedup_skip", reason="semantically_similar", user_id=mem0_uid)
            else:
                await asyncio.to_thread(
                    memory.add, 
                    fact_text, 
                    user_id=mem0_uid, 
                    infer=False,
                )
                audit_info("memory.write", "mem0_saved", user_id=mem0_uid, fact_chars=len(fact_text), topic_count=len(topics))
            
            # Invalidate memory context cache since memory was updated (M4 optimization)
            # Uses invalidate_on_write to signal WebSocket forwarder
            MemoryContextCache.invalidate_on_write(thread_id)
            
        except Exception as e:
            logger.warning("[Memory] Failed to save enriched memory: %s", e)
    
    return {"memory_invalidated": True}

