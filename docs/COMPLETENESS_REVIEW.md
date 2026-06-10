---
status: active
category: reference
last_updated: 2026-06-10
owner: human
audience: agent
---

# Owlynn Completeness Review — Frontier Chat & Co-Work Comparison

> **Purpose:** Snapshot of feature completeness vs frontier chat products (ChatGPT / Claude / Gemini) and co-work products (Cursor / Devin / Open WebUI / AnythingLLM). Use this to plan sprints, identify quick wins, and avoid re-discovering known gaps.

**Date:** 2026-06-10  
**Eval basis:** `local-frontier-eval-2026-06-11` (94.2% mechanical), `frontier-comparison-2026-06-11` (wins C1 vs raw DeepSeek)  
**Related:** [`COMPETITIVE_FEATURE_ANALYSIS.md`](COMPETITIVE_FEATURE_ANALYSIS.md) · [`STATUS.md`](STATUS.md) · [`BUG-TRACKER.md`](BUG-TRACKER.md)

---

## 1. Overall Scorecard

| Dimension | Owlynn (2026-06-10) | Frontier Chat (GPT-4o / Claude / Gemini) | Co-Work (Cursor / Open WebUI) |
|-----------|--------------------|-----------------------------------------|-------------------------------|
| Chat quality | ~94% mechanical; wins C1 head-to-head | Best in class | Varies |
| Tool-calling / agentic | ✅ LangGraph + security proxy | ✅ Good, no HITL | ✅ Cursor strongest |
| Memory (cross-turn) | ✅ **Best-in-class** (3-tier, cross-thread) | ❌ Session-only | ❌ Mostly none |
| Privacy / local-first | ✅ **Best-in-class** (anonymize + local fallback) | ❌ All cloud | ⚠️ Mostly cloud |
| Vision / multimodal | ⚠️ Partial (Florence proxy, image upload) | ✅ Native | ⚠️ Partial |
| Voice (STT) | ❌ TTS only — STT removed | ✅ Advanced Voice Mode | ❌ Usually none |
| Document RAG (auto-folder) | ⚠️ File watcher + Qdrant, no seamless UX | ❌ None built-in | ⚠️ GPT4All LocalDocs best |
| Model management | ❌ LM Studio dependency | ✅ Managed | ⚠️ Jan / LM Studio |
| Persona / agents | ✅ Persona system + skills | ⚠️ GPTs / Projects | ✅ Open WebUI |
| Plugin / extensions | ⚠️ MCP + 20 built-in | ✅ Plugin store | ✅ Marketplace |
| Programmatic API | ✅ `/v1/chat/completions` + CLI | ✅ | ✅ |
| Security / HITL | ✅ **Unique** — no competitor has this | ❌ None | ❌ None |
| Latency (TTFT) | ⚠️ <8s SLO met on M4; local Qwen 5–30s | <2s cloud | <2s cloud |
| UI polish | ⚠️ Functional glassmorphic; some rough edges | ✅ Excellent | ✅ Excellent |
| Eval score | **94.2%** mechanical (target ≥97%) | N/A | N/A |

---

## 2. What Is Solidly Complete ✅

### Agent Orchestration
- LangGraph: `memory_inject → router → simple/complex → tools → memory_write`
- 3-way routing: `simple` (1B MiniCPM5) · `complex-default` (Qwen 9B) · `complex-cloud` (DeepSeek V4)
- Security proxy + plan review HITL — **no competitor has this**
- Cloud payload: PII anonymization, stable/volatile layers, prefix-cache metrics

### Memory System (Unique vs frontier chat)
- Three-tier: JSON STM · Qdrant/Mem0 LTM · personal topics/interests/conversations
- Split inject: `memory_inject_lite` (fast, no vector) → router gate → `memory_retrieve`
- Background Qwen extraction (Redis stream → idle-deferred LTM writes)
- Validated in eval: session recall M1.2=100, LTM cross-thread M2.1=100

### Tool Suite (20+ tools)
| Category | Tools |
|----------|-------|
| Web | `web_search`, `fetch_webpage`, `deep_research` |
| Files | CRUD workspace files (HITL gated on writes/deletes) |
| Documents | `create_docx`, `create_xlsx`, `create_pptx`, `create_pdf` |
| Compute | `notebook_run` (stateful Python REPL) |
| Screen Assist | tmux, macOS AX, browser context, Kali SSH |
| Memory | `recall_memories`, `recall_all_memories`, `search_workspace_docs` |
| Tasks/Skills | `todo_*`, `list_skills`, `invoke_skill` |
| HITL | `ask_user` |

### Cloud Architecture
- DeepSeek V4 flash/pro, 1M token context, circuit breaker, jittered retries
- macOS Keychain key storage; PII scrub before any cloud call
- Vision proxy: Florence-2 → OCR text → DeepSeek text-only path
- Session cost tracker + cloud usage chip in UI

### Testing
- ~919 pytest + 111 vitest; property-based + contract suites
- Frontier eval harness: 19-turn, **94.2%** post-fix
- Local CI: `scripts/ci.sh` + pre-push hook

---

## 3. Partially Built — Active Gaps ⚠️

### 3.1 Vision Route Fragility
**What works:** Composer drag-and-drop, Florence-2 lazy load, vision proxy for cloud path.  
**What's broken:** F9.1 eval only 60–100% depending on Florence load variance; image attach does not deterministically trigger `vision_cloud` route. Cloud + image = best path often missed.  
**Tracked as:** BUG-17 (see `BUG-TRACKER.md`)

### 3.2 Simple-Path Empty Reply
Simple node occasionally returns an empty visible bubble — streaming chunk doesn't surface in UI even when route + model badge are correct.  
**Impact:** Basic chat reliability gap vs any frontier product.  
**Tracked as:** BUG-18

### 3.3 Tool-Call Text Leaks
F3/F4 eval: `<tool_call>` XML leaks as literal text in assistant response instead of executing. Qwen fallback path most likely.  
**Impact:** User-visible corruption; judge penalises clarity.  
**Tracked as:** BUG-19

### 3.4 M4 Greeting Gate (Router)
M4.1 eval: `"Hi there!"` routed to `complex-cloud` instead of `simple`. Trivial inputs waste cloud tokens and add latency.  
**Impact:** Cost + TTFT regression on greetings.  
**Tracked as:** BUG-20

### 3.5 Document RAG UX
File watcher + Qdrant + `search_workspace_docs` exist, but:
- No indexing progress UI (progress %, file states)
- W1.1 eval: tool card missing in timeline within timeout
- No hybrid BM25 + vector search (pure vector only)
- No GPT4All-style "drop a folder → ask questions" seamless flow

### 3.6 Token Budget / Cloud Budget WS Events
`token_budget_update` and `cloud_budget_warning` are **documented in CHAT_PROTOCOL.md as planned but not implemented**. Users have no real-time budget visibility.

### 3.7 UI Polish Gaps
- No conversation search / thread organization (pin, tag, date groups)
- No in-app model browser (must use LM Studio)
- No chat format templates / per-model prompt presets
- Electron "on hold" — Safe Mode, Screen Assist window sizing need desktop mode

---

## 4. Missing vs Frontier ❌

### 4.1 Voice Input (STT) — Removed, Not Replaced
Live Talk removed April 2026; only `speak_text` TTS remains.  
**Recommended:** Push-to-talk Whisper (`faster-whisper tiny.en`), 2–4 days effort.

### 4.2 Response Coherence / Self-Correction
No mechanism to detect wrong answers or retry on quality. HITL.md documents this as a known architectural gap. Cursor / Devin both have feedback loops (compiler, test runner).

### 4.3 In-App Model Management
No model browser, no HF search, no one-click assignment. All config via `defaults.yaml` / `.env`.

### 4.4 Co-Work / Pair Programming Depth (vs Cursor)
No LSP integration, no diff/patch view (write = overwrite), no git blame/AST context, no compiler feedback loop.

---

## 5. Comparison Summaries

### vs ChatGPT / Claude / Gemini

| Feature | Owlynn | Frontier Chat |
|---------|--------|--------------|
| Memory | ✅ **Better** (persistent, semantic, cross-thread) | ❌ Session-only |
| Privacy | ✅ **Better** (local-first, anonymization) | ❌ All cloud |
| Voice | ❌ TTS only | ✅ Full STT+TTS |
| Vision | ⚠️ Fragile proxy | ✅ Native, fast |
| Reliability | ⚠️ Empty bubble, tool leaks | Very high |
| Cost | ✅ Very low (local + cheap DeepSeek) | High subscription |

### vs Open WebUI / AnythingLLM

| Feature | Owlynn | Open WebUI | AnythingLLM |
|---------|--------|-----------|------------|
| Agent orchestration | ✅ **Best** (LangGraph + HITL) | ⚠️ Basic | ⚠️ Basic |
| Tool extensibility | ⚠️ MCP + built-in | ✅ Marketplace | ✅ Marketplace |
| Document RAG | ⚠️ Partial auto-index | ✅ Full | ✅ Full |
| Multi-user | ❌ By design | ✅ | ✅ |

### vs Cursor / Devin

| Feature | Owlynn | Cursor | Devin |
|---------|--------|--------|-------|
| Long-horizon memory | ✅ **Better** | ❌ Session-only | ⚠️ Notes only |
| Privacy | ✅ **Best** | ❌ Cloud | ❌ Cloud |
| Editor integration | ❌ Companion app | ✅ Native | ✅ Native |
| Terminal feedback loop | ⚠️ Notebook + tmux | ✅ Native | ✅ Native |

---

## 6. Priority-Ranked Improvement Plan

### 🔴 Tier 1 — Reliability Bugs (Must Fix)

| # | Gap | Effort | File(s) |
|---|-----|--------|---------|
| BUG-17 | **Vision route determinism** — image doesn't trigger `vision_cloud` | 1–2 days | `router.py`, `vision_proxy.py` |
| BUG-18 | **Simple-path empty reply** — streaming bubble doesn't render | 1–2 days | `simple.py`, `ws/handler.py` |
| BUG-19 | **Tool-call text leaks** — `<tool_call>` in user-visible reply | 1 day | `complex.py`, `formatter.py` |
| BUG-20 | **M4 greeting gate** — trivial inputs routed to cloud | Half day | `router.py` |

### 🟡 Tier 2 — High-Impact Features

| # | Feature | Effort | Impact |
|---|---------|--------|--------|
| IMP-1 | **Token budget + cloud budget WS events** — implement planned events | 1–2 days | Transparency, UX |
| IMP-2 | **Document RAG UX** — indexing progress, hybrid search, folder-drop | 3–5 days | GPT4All parity |
| IMP-3 | **Voice input push-to-talk Whisper** | 2–4 days | Frontier parity |
| IMP-4 | **Thread organization** — search, pin, tags, date grouping | 2–3 days | Growing history UX |

### 🟢 Tier 3 — Strategic / Longer Horizon

| # | Feature | Effort | Impact |
|---|---------|--------|--------|
| IMP-5 | **In-app model browser** (LM Studio list + HF search + assign) | 3–5 days | Model management UX |
| IMP-6 | **Electron revival** — Safe Mode, Screen Assist in desktop | 1 week | Desktop completeness |
| IMP-7 | **Response coherence / self-correction loop** | 1–2 weeks | Quality vs Cursor |
| IMP-8 | **Coding pair-programming depth** — diff view, LSP hooks, git context | 2–3 weeks | vs Cursor |

---

## 7. Eval Progress to Target

| Run | Score | Status |
|-----|-------|--------|
| v8 (6-turn cloud) | 75.8% | Superseded |
| v9 pre-fix (19-turn) | 82.4% | Superseded |
| v9b post-fix | **94.2%** | Current best |
| **Target** | **≥97%** | **~3% gap** |

**To close the 3% gap:** Fix BUG-18 (F1, +5 pts) + BUG-20 (M4, +5 pts) + BUG-17 (F9, +2–5 pts) + F6 STM/tool distinction (+2 pts).

---

## 8. Owlynn's Moat (Irreplaceable Differentiators)

1. **LangGraph HITL security proxy** — tool calls gated by human approval; no competitor has this
2. **Local-first with PII anonymization on cloud escalation** — data never leaves machine unredacted
3. **Persistent semantic memory across sessions** — frontier chat has session memory only
4. **Pentest/research scenario playbooks** — L2/L3 context loading for specialized workflows
5. **Cost** — local Qwen 9B fallback + DeepSeek flash ≈ near-zero marginal cost vs $20/month

---

## Related

- [`COMPETITIVE_FEATURE_ANALYSIS.md`](COMPETITIVE_FEATURE_ANALYSIS.md) — detailed feature-by-feature gap vs local AI platforms
- [`BUG-TRACKER.md`](BUG-TRACKER.md) — BUG-17..20 (new open bugs from this review)
- [`ENGINEERING_IMPROVEMENTS.md`](ENGINEERING_IMPROVEMENTS.md) — IMP-1..8 improvement backlog
- [`STATUS.md`](STATUS.md) — current remaining tasks and risks
- [`evaluations/local-frontier-eval-2026-06-11.md`](evaluations/local-frontier-eval-2026-06-11.md) — mechanical eval basis
- [`evaluations/frontier-comparison-2026-06-11.md`](evaluations/frontier-comparison-2026-06-11.md) — quality A/B basis

## Last updated

2026-06-10 — initial completeness review; BUG-17..20 + IMP-1..8 identified
