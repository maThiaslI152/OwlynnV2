---
last_verified: 2026-05-26
auto_generated: false
---

# Owlynn Project Guide (Human)

## Overview

Owlynn is a local-first AI coworker that runs a LangGraph agent backend with a Tauri frontend. Keeps most reasoning and data on your machine while supporting optional cloud escalation and external tools.

## Entry Points

```text
src/api/server.py                              # Backend entry point
frontend-v2/src/App.tsx                        # Frontend entry point
docs/ARCHITECTURE_OVERVIEW.md                  # Full architecture
docs/AGENT_FLOW.md                             # LangGraph node details
docs/TOOLS.md                                  # Tool reference
docs/API_REFERENCE.md                          # REST/WS endpoints
```

## Architecture

| Layer | Technology | Location |
|-------|-----------|----------|
| Frontend | Tauri + React/TypeScript | `frontend-v2/` |
| Backend | FastAPI + WebSocket streaming | `src/api/server.py` |
| Agent orchestration | LangGraph nodes | `src/agent/` |
| Memory | JSON + Mem0/Qdrant | `src/memory/` |
| Tools | File ops, web, notebook, docs, skills, MCP | `src/tools/` |

## Flow

1. User message enters WebSocket chat endpoint
2. Memory context is injected
3. Router chooses simple vs complex model path
4. Complex path may call tools through security proxy approval
5. Response is streamed back and memory is updated

## Testing

### Local Development Checklist

```bash
pip install -r requirements.txt
# Start supporting services (Redis/Qdrant etc.)
python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000
pytest tests/ -v
cd frontend-v2 && npx vitest run
```

## Key Decisions

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| Local-first architecture | Data privacy, offline operation | Cloud fallback requires API keys |
| Security proxy HITL | Safe tool execution | Approval latency for sensitive operations |
| LangGraph orchestration | Stateful, testable graph | More complex than linear pipelines |

## Configuration

Current priorities:
- Stabilize hybrid model routing (small/medium/cloud DeepSeek pathing)
- Keep tool-call reliability high under local model edge cases
- Maintain clean project-level workflow
- Improve startup and MCP resilience under flaky network conditions

Delivery conventions:
- Keep feature changes scoped and test-backed
- Prefer focused PRs over large mixed commits
