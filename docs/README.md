---
status: active
category: reference
audience: agent
last_updated: 2026-06-10
owner: ai-agent
---

# docs/ — Project Documentation Map

> **Purpose:** Documentation index and reading order. Agents start at [`AGENTS.md`](../AGENTS.md); humans start at [`README.md`](../README.md).

## For AI agents

```
AGENTS.md → PROJECT_GUIDE.md → architecture/overview.md → task doc
```

| Step | Document | Why |
|------|----------|-----|
| 0 | [`guides/dev-startup.md`](guides/dev-startup.md) | Run the app (`setup.sh`, `start.sh`) |
| 1 | [`PROJECT_GUIDE.md`](PROJECT_GUIDE.md) | File map by task |
| 2 | [`architecture/overview.md`](architecture/overview.md) | System modules and data flow |
| 3 | Task doc | `EXTENDING_AGENT.md`, `CHAT_PROTOCOL.md`, `TOOLS.md`, `MEMORY.md`, `HITL.md`, or `debugging/README.md` |

Filter all docs via [`INDEX.md`](INDEX.md) (`audience: agent`).

## For humans

```
README.md → CONTRIBUTING.md → guides/dev-startup.md
```

Historical context: [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md), [`PROJECT_TIMELINE.md`](PROJECT_TIMELINE.md), [`STATUS.md`](STATUS.md).

## Structure

```
docs/
├── README.md                 # This file
├── INDEX.md                  # Machine-readable manifest (v6, audience tags)
├── PROJECT_GUIDE.md          # Canonical agent file map
├── architecture/overview.md  # System design
├── debugging/                # Symptom → subsystem guides
├── guides/                   # How-to (dev-startup, lm_studio, …)
├── standards/                # coding-style, documentation
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

2026-06-10 — agent-first documentation overhaul
