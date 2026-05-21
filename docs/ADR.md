# Architecture Decision Log (ADR)

This log records the significant architectural decisions for the Owlynn project,
following the [ADR pattern](https://adr.github.io/). Each entry captures the context,
decision, and consequences of a key design choice.

## ADR-0001: Tauri as Desktop Shell

**Date:** 2026-04-23

**Status:** Implemented with Tauri v2.10.3 (migrated from v1.5).

**Context:** Owlynn needed a native desktop shell to support local-first operation with
screen capture, push-to-talk, and security controls. Options included Electron, Tauri v1/v2,
and bare Python GUI frameworks.

**Decision:** Tauri desktop shell with React + TypeScript frontend, using macOS native vibrancy.

**Consequences:**

- Native window management and OS-level permissions (screen capture, mic) via Tauri commands.
- Rust backend for security-critical paths, separate from Python agent.
- Smaller binary size compared to Electron (~5MB vs ~100MB).
- Migration to Tauri v2 is complete (see ADR-0013): updated `tauri.conf.json` schema,
capability-based permissions, event/command APIs, and frontend imports.
- Requires Tauri permission audit before production release.

---

## ADR-0002: LangGraph for Agent Orchestration

**Date:** 2026-04-23

**Context:** The agent needs a stateful, cyclic execution graph for routing, tool execution,
memory management, and security gating. Options included LangGraph, custom state machines,
and other agent frameworks.

**Decision:** LangGraph with Python `StateGraph` and `AgentState` TypedDict.

**Consequences:**

- State transitions are explicit and testable via conditional edges.
- Supports cyclic flows (tool call → security → action → LLM loop).
- Redis-backed checkpointing for persistence across restarts.
- Checkpoint system enables thread-level conversation history.

---

## ADR-0003: Local-First Hybrid Model Architecture

**Date:** 2026-04-23

**Context:** The assistant must work fully offline while optionally escalating to cloud models
for complex tasks. Models need tiered routing based on task complexity.

**Decision:** Three-tier model system: Small LLM (always local), Medium LLM (local, default),
Large LLM (optional cloud via DeepSeek).

**Consequences:**

- Small LLM (`gemma-4-e2b-heretic-uncensored-mlx`, 4K context) for routing and simple tasks.
- Medium LLM (`lfm2-8b-a1b-absolute-heresy-mpoa-mlx`, 100K context) for complex tasks.
- Cloud fallback (DeepSeek) for coding and long-context tasks when available.
- `LLMPool` manages lifecycle — clears when profile changes trigger model swap.
- Model keys stored in runtime profile, changeable without server restart.

---

## ADR-0004: WebSocket as Primary Frontend-Backend Transport

**Date:** 2026-04-23

**Context:** The frontend needs real-time streaming of LLM responses, tool execution events,
and voice state changes. REST polling would be too slow for chat UX.

**Decision:** Single persistent WebSocket connection per thread (`/ws/chat/{thread_id}`)
with JSON event framing.

**Consequences:**

- Event types defined in `docs/CHAT_PROTOCOL.md` with strict shape contracts.
- `WsClient` TypeScript wrapper provides lifecycle callbacks and send-gating.
- Rust Tauri events (voice, screen assist) are forwarded through a parallel channel.
- Connection established per-thread; disconnects don't cancel running graph execution.

---

## ADR-0005: Mem0 + Qdrant for Long-Term Memory

**Date:** 2026-04-23

**Context:** The assistant needs persistent cross-session memory with semantic search.
Options included Mem0 with FAISS, ChromaDB, or Qdrant.

**Decision:** Mem0 with local Qdrant on port 6333, LM Studio embeddings
(`nomic-embed-text-v1.5`).

**Consequences:**

- Memory is namespace-scoped by project (`project:<id>`) and user identity.
- Topic extraction and enriched memory save on every conversation turn.
- Memory context TTL-cached (5 min) in `MemoryContextCache` for M4 optimization.
- Requires Qdrant container running for memory functionality.

---

## ADR-0006: Security Proxy with HITL Approval

**Date:** 2026-04-23

**Context:** The agent needs guardrails around destructive actions (file deletion,
code execution, data modification). The system must support both automatic approval
and human-in-the-loop authorization.

**Decision:** Mandatory `security_proxy` node in LangGraph graph with risk classification
and configurable execution policy (`hitl` / `auto_approve`).

**Consequences:**

- Every tool call goes through security proxy before execution.
- Risk metadata (label, confidence, rationale, remediation) is classified server-side.
- Frontend shows `ActionProposalQueue` for pending approvals.
- Audit trail of all tool executions with hash-verified export.

---

## ADR-0007: Redis for Hot State, Qdrant for Vector Memory

**Date:** 2026-04-23 (updated 2026-04-23 to reflect actual Qdrant usage)

**Context:** The agent needs fast session state (active conversations) and durable
vector storage (long-term memory, semantic search).

**Decision:** Redis for session state and LangGraph checkpointing; Qdrant for vector
memory (accessed via Mem0); SearxNG for local web retrieval.

**Consequences:**

- Redis provides sub-millisecond session state access.
- Qdrant (on port 6333) with `nomic-embed-text-v1.5` embeddings for memory vector storage.
- Mem0 wraps Qdrant for higher-level memory operations (topic extraction, enriched memory).
- SearxNG enables privacy-preserving local web search.
- Qdrant, Redis, and SearxNG run in containers (`docker-compose.yml`).

---

## ADR-0008: Unfiltered Content Policy with Strict Tool Controls

**Date:** 2026-04-23

**Context:** The assistant is designed for a personal-use local assistant with no
content-behavior filters, but must maintain security around destructive actions.

**Decision:** No content-behavior filters applied to model outputs. Strict tool-level
permissions with destructive-action confirmations and tamper-evident audit trail.

**Consequences:**

- Models produce unfiltered output (user is responsible for content).
- Tool execution requires explicit approval for risky operations.
- All tool actions are logged with HMAC-signed audit hashes.
- Audit bundles can be exported and verified for tamper evidence.

---

## ADR-0009: Zustand for Frontend State Management

**Date:** 2026-04-23

**Context:** The React frontend needs a simple, typed state store that integrates with
WebSocket events and Tauri runtime events without boilerplate.

**Decision:** Zustand with single `useAppStore` store for all frontend state.

**Consequences:**

- No Redux middleware or context provider nesting required.
- State mutations are colocated with the store definition.
- `verbatimModuleSyntax` requirement in TypeScript config.
- TypeScript types for `ChatMessage`, `ToolExecutionSnapshot`, `ActionProposal` etc.

---

## ADR-0010: WebSocket Event Telemetry for Routing and Fallback Visibility

**Date:** 2026-04-23

**Context:** Without runtime visibility into routing decisions and model fallback chains,
debugging unexpected behavior is difficult. The backend needed to expose internal
orchestration state to the frontend.

**Decision:** Emit `router_info` event on every routing decision and `fallback_chain`
in `model_info` events.

**Consequences:**

- `router_info` contains route, confidence, reasoning, classification_source, features.
- `fallback_chain` tracks ordered model attempts with status, reason, duration_ms.
- Both events have WS contract tests (`test_ws_router_info_event_emitted`, etc.).
- Frontend `OrchestrationPanel` displays routing and model information.
- Non-serializable metadata fields silently dropped with warning log.

---

## ADR-0011: Auto-Summarize with Multi-Level Compression

**Date:** 2026-04-23

**Context:** Long-running conversations can exceed the model's context window.
A naive truncation would lose important context. The system needed automatic
context compression.

**Decision:** Auto-summarize LangGraph node triggered at >85% context window usage,
with structured categorized output and prior-summary awareness.

**Consequences:**

- Small LLM produces structured summary (decisions, facts, preferences, tasks, code).
- Prior auto-summaries are fed back into subsequent compression rounds.
- Protected messages (tool results, pinned, system) are never compressed.
- `context_summarized` WebSocket event emitted on compression.
- Graceful degradation — LLM failure results in no-op (keep full context).

---

## ADR-0012: macOS-Native Live Talk Runtime via Tauri Events

**Date:** 2026-04-24

**Status:** SUPERSEDED by ADR-0013 (2026-04-24), then REMOVED (2026-04-29)

**Context:** Live Talk needed to move from UI placeholders to a desktop-native voice runtime
for personal assistant workflows (wake-word style listening, push-to-talk, and TTS response playback),
without introducing a separate backend voice service.

**Decision:** Implement Live Talk in the Tauri Rust layer and forward voice lifecycle events through
`owlynn://runtime-event`, while keeping agent input unified as normal `user.message` chat events.

**Consequences:**

- New Tauri commands: `start_voice_listening`, `stop_voice_listening`, `set_wake_word_phrase`,
`start_push_to_talk`, `stop_push_to_talk`, `hard_stop_voice`, `speak_text`.
- New runtime voice events: `voice.state`, `voice.transcript`, `voice.wake_word`,
`voice.error`, `voice.tts_state`, `voice.started`.
- Frontend listens to runtime events and submits final transcript as `user.message`
with `source: "voice"` so the Python/LangGraph backend remains unchanged.
- macOS permission assets required: `Entitlements.plist` and `Info.plist`
entries for microphone/speech recognition.
- Real ObjC FFI implementation replaces initial simulation: SFSpeechRecognizer streaming
with AVAudioEngine mic capture (`installTapOnBus:bufferSize:format:block:`),
block-based result handler (`recognitionTaskWithRequest:resultHandler:`), constrained
phrase detection for wake-word, per-segment confidence extraction, and cleanup lifecycle
(stop engine, remove tap, cancel/finish task, release ObjC objects). TTS via
NSSpeechSynthesizer (ObjC FFI polling loop) with `say` command fallback.
- **Critical bug — non-null-terminated C strings passed to ObjC FFI (2026-04-24 fix):**
Three `msg_send![class!(NSString), stringWithUTF8String: ...]` calls passed
Rust `&str` pointers directly without null terminators. `stringWithUTF8String:`
reads until a `\0` byte, so unterminated reads corrupt adjacent ObjC runtime
memory (class metadata, string caches). This caused a deterministic `SIGBUS`/`EXC_BAD_ACCESS`
crash at address `0x53552d6e80` in WebKit's `WKContentWorld` via `_CFRelease` → `_xzm_free`
— an apparently unrelated subsystem but actually the victim of prior memory corruption.
**Fix:** All three call sites changed to use `CString::new(str)` which guarantees
null-terminated UTF-8. See `src-tauri/src/voice/mod.rs` lines 287, 338, 662.
- **Debug .app bundle requirement:** `tauri dev` runs the binary directly without
an `.app` wrapper, so macOS TCC cannot read `Info.plist`. A debug `.app` bundle must
be built via `tauri build --debug` and launched via `open`. `start.sh` handles this
automatically.
- **macOS 26.4 WebKit transparent window crash:** `transparent: true` with
`titleBarStyle: "Overlay"` / `hiddenTitle: true` triggers a WebKit GPU compositing
crash on macOS Sequoia 26.4. The opaque window workaround (`transparent: false`,
no overlay title bar) is required. Frontend CSS was updated so `body.tauri-glass`
uses a dark gradient instead of `background: transparent`.
- **Full crash analysis:** See `[docs/archive/OBJC_FFI_CRASH.md](docs/archive/OBJC_FFI_CRASH.md)` for
the complete root-cause analysis of the non-null-terminated C string crash and the
macOS 26.4 transparent window crash.

---

## ADR-0013: Tauri v2 + Swift Helper for Two-Stage Voice Pipeline

**Date:** 2026-04-24

**Status:** REMOVED (2026-04-29) — Live Talk voice pipeline removed from codebase. Only `speak_text` TTS remains.

**Context:** The previous Live Talk implementation used direct ObjC FFI from Rust with
`SFSpeechRecognizer` for both wake-word and transcription, and exposed push-to-talk controls.
The new target stack requires a two-stage architecture with SoundAnalysis wake-word detection,
WhisperKit transcription optimized for Apple Neural Engine, and a migration to current stable
Tauri APIs.

**Decision:** Migrate desktop runtime to Tauri v2 and orchestrate voice through a Swift helper
subprocess (`whisperkit-helper`) using line-delimited JSON over stdin/stdout:

- Stage 1: SoundAnalysis + CoreML wake-word model (`Athena`)
- Stage 2: WhisperKit `openai_whisper-large-v3-v20240930_turbo` transcription (see `docs/archive/LIVE_TALK_VOICE_PROCESSING_AND_VAD.md`)
- Push-to-talk removed from command surface and UI

**Consequences:**

- Rust command/event APIs updated for Tauri v2 (`emit`, `get_webview_window`, capabilities).
- Frontend bridge updated to `@tauri-apps/api` v2 imports.
- Wake-word phrase is fixed to `Athena` (`get_wake_word_phrase` remains for compatibility).
- macOS minimum runtime target raised to 14.0 for stable ANE execution profile.
- Direct Rust ObjC voice coupling is reduced; Swift-native frameworks live in the helper process.