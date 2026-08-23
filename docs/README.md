---
status: active
category: reference
audience: agent
last_updated: 2026-08-23
owner: ai-agent
---

# docs/ — Project Documentation Map

> **Purpose:** Documentation index and reading order. Agents start at [`AGENTS.md`](../AGENTS.md); humans start at [`README.md`](../README.md).

## For AI agents

```
AGENTS.md → docs/development/PROJECT_GUIDE.md → docs/architecture/overview.md → task doc
```

| Step | Document | Why |
|------|----------|-----|
| 0 | [`guides/dev-startup.md`](guides/dev-startup.md) | Run the app (`setup.sh`, `start.sh`) |
| 1 | [`development/PROJECT_GUIDE.md`](development/PROJECT_GUIDE.md) | File map by task |
| 2 | [`architecture/overview.md`](architecture/overview.md) | System modules and data flow |
| 3 | Task doc | `development/EXTENDING_AGENT.md`, `development/CHAT_PROTOCOL.md`, `features/TOOLS.md`, `features/MEMORY.md`, `HITL.md`, or `debugging/README.md` |

Filter all docs via [`INDEX.md`](INDEX.md) (`audience: agent`).

## For humans

```
README.md → CONTRIBUTING.md → guides/dev-startup.md
```

Historical context: [`architecture/PROJECT_OVERVIEW.md`](architecture/PROJECT_OVERVIEW.md), [`PROJECT_TIMELINE.md`](PROJECT_TIMELINE.md), [`STATUS.md`](STATUS.md).

## Structure

```
docs/
├── README.md                 # This file
├── INDEX.md                  # Machine-readable manifest (v24, audience tags)
├── development/              # Canonical agent file maps, extending agent, chat protocol
├── architecture/             # System design, agent flow, redis lifecycle, vision proxy
├── debugging/                # Symptom → subsystem guides
├── features/                 # Tools, memory, modes, web search
├── guides/                   # How-to (dev-startup, lm_studio, …)
├── standards/                # coding-style, documentation, evaluation
├── archive/                  # Superseded (audience: archive)
├── evaluations/              # Eval reports (audience: archive)
└── changes/                  # Past feature changelogs (audience: archive)
```

## Key resources outside docs/

| Path | Purpose |
|------|---------|
| [`AGENTS.md`](../AGENTS.md) | Agent entry point |
| [`src/config/defaults.yaml`](../src/config/defaults.yaml) | Configuration source of truth |
| [`.cursor/rules/agent-onboarding.mdc`](../.cursor/rules/agent-onboarding.mdc) | Always-on agent navigation rule |
| [`scripts/ci.sh`](../scripts/ci.sh) | Local CI |

## Related

- [`INDEX.md`](INDEX.md) — full manifest
- [`standards/documentation.md`](standards/documentation.md) — doc authoring rules

## Last updated

2026-08-23 — Thought Graph & Mindmap Canvas UI Architecture: Replaced legacy left sidebar with full-width Coggle Organic Mindmap (Normal/Study) & Autodesk Maya Hypershade Node Editor (Pentest), top MacMenuBar mode switcher, real-time Brave extension status, and persistent thought graph engine.
2026-08-23 — Unified Gemma 4 12B Agentic Q4 architecture, speculative decoding safeguards, deterministic tool ordering, and full 100% CI green.
2026-08-22 — Backbone modernization, prompt cache stability, dynamic ToolRegistry, and full CI green
