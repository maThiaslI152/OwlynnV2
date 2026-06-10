---
status: active
category: guide
last_updated: 2026-06-09
owner: ai-agent
---

# Phase 1: Memory Orchestration

Four-tier memory pipeline with sub-300ms router path, async custom extraction, and pentest/research scenarios.

## Architecture

```text
memory_inject_lite → router → memory_retrieve → summarize_gate → …
        │                │            │
        │                │            └─ Qdrant (gated) + scenario markdown
        │                └─ needs_memory_retrieval, scenario_id
        └─ profile, persona, topics (no vector search)

memory_write → PII scrub → Redis stream → 8B extractor worker → Qdrant (L1 atoms)
```

## Tiers

| Tier | Storage | Content |
|------|---------|---------|
| **L0** | Qdrant | Raw chunks (optional; L1-first in Phase 1) |
| **L1** | Qdrant via Mem0 | Structured atoms (`jsdoc` / `docstring` / `json`) |
| **L2** | `scenarios/*/playbook.md` | Pentest / research workflows |
| **L3** | `scenarios/*/constraints.md` | OPSEC, citation rules |

## Key modules

| Path | Role |
|------|------|
| `src/agent/nodes/memory.py` | `memory_inject_lite`, `memory_retrieve`, async `memory_write` |
| `src/agent/pii_scrubber.py` | PII scrub before LTM writes |
| `src/memory/extraction/` | Custom 8B prompts, schema, Redis worker |
| `src/memory/scenarios.py` | Scenario detect + markdown loader |
| `src/memory/compression.py` | Dense memory block for cloud brief |
| `scenarios/pentest/`, `scenarios/research/` | L2/L3 markdown |

## Router fields

LLM classifier JSON (optional):

```json
{
  "routing": "complex",
  "needs_memory_retrieval": true,
  "scenario_id": "pentest"
}
```

Deterministic paths set `needs_memory_retrieval` explicitly (e.g. greetings → `false`, knowledge-cache bypass → `false`).

## Extraction contract

Worker output (no `mem0 infer=True`):

```json
{
  "atoms": [{
    "tier": "L1",
    "format": "jsdoc",
    "content": "/** @fact preferred_region ap-southeast-1 */",
    "tags": ["pentest"],
    "confidence": 0.9
  }]
}
```

## Configuration (`defaults.yaml`)

```yaml
memory:
  extraction:
    temperature: 0.1
    max_tokens: 1024
    idle_cooldown_seconds: 8
    idle_poll_seconds: 2
    max_idle_wait_seconds: 600
    defer_while_graph_active: true
    process_nice: 10
  cloud_inject_max_chars: 800
```

Background extraction defers Qwen until chat idle — see [MEMORY.md](../MEMORY.md) and `src/agent/local_llm_scheduler.py`.

Redis stream: `owlynn:memory:extract` (consumer group `owlynn-extractors`).

## Tests

```bash
PYTHONPATH=$(pwd) python -m pytest -q \
  tests/test_phase1_memory_orchestration.py \
  tests/test_memory_retrieve_gate.py \
  tests/test_memory_nodes.py

# Full automated pipeline smoke (inject → router → retrieve → write → worker)
./scripts/test_memory.sh
```

## Next phases

- **Phase 2:** [VISION_PROXY.md](../architecture/VISION_PROXY.md)
- **Phase 3:** [screen-assist-phase3.md](./screen-assist-phase3.md)
- **All phases:** [memory-vision-screen-roadmap.md](./memory-vision-screen-roadmap.md)

## Related

- [MEMORY.md](../MEMORY.md)
- [personal_assistant_memory.md](./personal_assistant_memory.md)
