---
last_verified: 2026-05-26
auto_generated: false
---

# Owlynn Project Guide (AI Agent)

## Overview

Owlynn is a local-first AI coworker. Prioritize reliability, traceability, and safe tool usage over novelty. Keep changes explainable and compatible with local runtime constraints.

Navigation companion: `docs/AI_AGENT_INDEX.md`

## Entry Points

```text
src/agent/                    # Routing, model selection, graph orchestration, security gating
src/api/                      # HTTP + WebSocket app surface
src/tools/                    # Tool implementations exposed to agent
src/memory/                   # Persona/profile/project/user memory components
frontend-v2/                  # Desktop UI shell and interaction modules
tests/                        # Behavior, property, and regression tests
```

## Architecture

### Execution Rules

1. Keep diffs focused to the user request
2. Preserve security proxy behavior around tool execution
3. When touching routing/model behavior, update or add targeted tests
4. Avoid mixing unrelated frontend/backend/docs changes in one commit
5. Prefer deterministic fallbacks over silent failure paths

### Model-Routing Expectations

| Concern | Requirement |
|---------|-------------|
| Router | Decides among: simple, complex-default, vision, long-context, cloud |
| Complex node | Must preserve safe tool binding, fallback chain visibility, blank-response fallback, anonymization/deanonymization correctness for cloud paths |

## Testing

### Minimum Coverage by Area

| Change Area | Required Tests |
|-------------|---------------|
| Model/routing | `tests/test_llm_pool.py`, `tests/test_swap_manager.py`, `tests/test_router_web_intent.py` |
| Anonymization | `tests/test_anonymization*.py` |
| Fallback behavior | `tests/test_complex_node_properties.py` |

### Definition of Done

1. Code compiles and tests pass for changed area
2. User-facing behavior is verified (or explicitly noted if not runnable)
3. Documentation updated when behavior/workflow changes

## Key Decisions

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| Security proxy gating all tools | Safety for destructive operations | Extra hop per tool call |
| Deterministic fallbacks preferred | Predictable behavior | May not always choose optimal model |
| Single Zustand store | Simple state management | No store segmentation |

## Configuration

No specific env vars for agent guidelines. Rules enforced via code review and testing policy.
