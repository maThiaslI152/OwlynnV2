---
status: active
category: reference
last_updated: 2026-05-31
owner: human
---

# OwlynnV2 Project Overview

> **Purpose:** High-level project overview covering goals, architecture, progress, and areas for improvement.

**Date:** 2026-05-27

This document provides a high-level summary of the OwlynnV2 project, covering its goals, architectural overview, current progress, areas for improvement, and obsolete components.

---

## 1. Project Goal

Owlynn is a **local-first desktop AI coworker** designed primarily for developers and power users on Apple Silicon (e.g., M4 Air 24GB). 

**Core Objectives:**
- Keep user data entirely local, preserving privacy.
- Reason through complex tasks and execute tools (file operations, document generation, web search, code execution).
- Remember context across sessions via semantic vector memory.
- Safely gate sensitive tool operations behind human-in-the-loop (HITL) approval without sending data to the cloud (unless explicitly opted-in for fallback).

## 2. Overall Architecture

The system operates on a stateful, cyclic **LangGraph** architecture with a three-tier LLM routing strategy:
- **Backend:** Python 3.12+, FastAPI, LangGraph.
- **Frontend:** React 19, TypeScript (Vite 8), Zustand 5, wrapped in an Electron desktop shell.
- **LLM Tiers:**
  - **Small (Router):** `ibm-grok4-ultrafast-coder-1b` for quick classification.
  - **Medium (Reasoning):** `gemma-4-e4b-uncensored-hauhaucs-aggressive` for tool calling and reasoning.
  - **Cloud (Fallback):** DeepSeek API for escalated requests.
- **Memory System:** Three-tier architecture using Mem0 + Qdrant (long-term semantic), JSON files (short-term facts), and topic/interest tracking. Includes a zero-config workspace file watcher that auto-indexes documents into Qdrant for hybrid semantic search. PDF/DOCX extraction via Docling (layout-aware markdown with table structure detection).
- **Security:** A Security Proxy node that intercepts high-risk tool calls and requests user approval before execution.
- **Persona System:** Built-in profiles (Owlynn, Coder, Writer, Researcher) with custom JSON support, dynamically adjusting system prompts, tool permissions, and response tone via `persona_manager.py`.
- **OpenAI API Compatibility:** `POST /v1/chat/completions` endpoint with SSE streaming support, plus a Click CLI (`src/cli.py`) for terminal-based querying.

## 3. Project Progress

The project has successfully completed Phases 1 through 7, establishing a hardened MVP with a passing test suite (over 700 backend tests and 50+ frontend tests).

**Recent Milestones:**
- **SOTA Features Integration (May 2026):** Bridged competitive gaps with 3 new features — Dynamic Persona Selector (4 built-in profiles + custom JSON), OpenAI-Compatible local API server with SSE streaming CLI, and zero-config workspace RAG indexer with Qdrant vector search. Docling replaced PyMuPDF/python-docx for PDF/DOCX extraction (layout-aware, table detection). Full-stack browser testing confirmed all features operational.
- **MVP Hardening & Test Fixes:** Resolved environment config, dependency pinning, and skipped tests.
- **Skill Matching Improvements:** Fixed false-positive ambiguity triggers in the HITL gate and ensured confident skill matches bypass manual routing.
- **Frontend Markdown:** Replaced a limited custom parser with robust `react-markdown` + `remark-gfm` for full table and HTML rendering support.

**Current Active Phase (Phase 8 - Bug Fixes & Feature Integration):**
Addressing issues identified during the 2026-05-25 Browser Audit while integrating new capabilities. Key unresolved bugs include:
- **Critical:** System prompt/persona leaking into the first assistant response.
- **High:** Orchestration and Memory panels failing to load or showing blank data.
- **Medium:** Chat auto-titling defaulting to "New Chat", and Safe Mode lacking a browser fallback (Electron IPC dependency).

## 4. What Could Improve (Engineering Enhancements)

Several areas have been identified for future architectural and operational polish:

- **Automated CI:** The project deliberately remains strictly on local CI (`scripts/ci.sh`) to prevent GitHub Actions quota issues.
- **Frontend Resilience:** Increase unit and state testing around the Zustand store (`useAppStore`) and WebSocket lifecycles. Introduce React error boundaries to isolate panel failures.
- **Graceful Degradation:** Add timeouts, retries, and circuit breakers for external services (LM Studio, Qdrant, Mem0) so the application degrades gracefully when services are offline.
- **Security Defense-in-Depth:** Audit workspace file tools for path escapes (`..`), and consider stronger isolation boundaries for the Notebook/REPL tool.
- **Maintainability:** Split large CSS files (`index.css`), adopt structured logging, and optimize LLM concurrency to respect Apple Silicon unified memory constraints.

## 5. What is Obsolete / Removed

As the architecture has matured, certain features and implementations have been deprecated or removed to streamline the codebase:

- **Live Talk (Wake-word, STT):** Removed on 2026-04-29 to simplify the codebase and reduce maintenance burden, dropping voice interaction capabilities (though TTS remains active).
- **Custom Markdown Parser:** The legacy custom markdown parser located in `frontend-v2/src/lib/markdown.tsx` is no longer used by the `MessageContent` component, having been superseded by standard `react-markdown` ecosystem plugins.

---

*For detailed architectural decisions, see `ADR.md`. For live bug tracking, refer to `STATUS.md` and `BUG-ANALYSIS.md`.*

## Related

- [`docs/README.md`](README.md) — project documentation map
- [`docs/INDEX.md`](INDEX.md) — documentation index

## Last updated

2026-05-31 — `docs-standards-timeline` added frontmatter, purpose blockquote
