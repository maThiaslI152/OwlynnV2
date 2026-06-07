---
status: active
category: reference
last_updated: 2026-06-07
owner: ai-agent
---

# docs/ — Project Documentation Map

> **Purpose:** Project documentation map, reading order, and SDD workflow quick reference.

> **START HERE.** This is the project's documentation index and reading order for all agents and contributors.

## Reading Order (for new agents)

0. **Start the app:** [`docs/guides/dev-startup.md`](guides/dev-startup.md) — every prerequisite and step to get the full Owlynn app running
1. **This file** (`docs/README.md`) → [`docs/INDEX.md`](INDEX.md) → [`docs/PROJECT_TIMELINE.md`](PROJECT_TIMELINE.md)
2. **[`docs/architecture/overview.md`](architecture/overview.md)** — system context, modules, data flow
3. **[`specs/memory/constitution.md`](../specs/memory/constitution.md)** — non-negotiable rules
4. **[`docs/standards/coding-style.md`](standards/coding-style.md)** — formatting, naming, patterns
5. **Configuration:** [`src/config/defaults.yaml`](../src/config/defaults.yaml) — single source of truth for all settings
6. **Subsystem docs:** [`docs/HITL.md`](HITL.md) — safety gates · [`docs/MEMORY.md`](MEMORY.md) — memory tiers
7. **Active change context:**
   - `specs/active/<slug>/` — requirements, design, tasks
   - `.cursorplan/active/<slug>/plan.md` — canonical plan
   - `docs/changes/<slug>/CHANGELOG.md` — per-task edit history
8. **Then touch code.**

## Structure

```
docs/
├── README.md                      # This file — project map
├── INDEX.md                       # Machine-readable manifest
├── PROJECT_TIMELINE.md            # Aggregated project timeline
├── HITL.md                        # Human-in-the-Loop safety system documentation
├── MEMORY.md                      # Three-tier memory system documentation
├── architecture/
│   ├── overview.md                # System design overview
│   └── DEEPSEEK_V4_INTEGRATION.md # DeepSeek V4 API, caches, deferred Phase 5
├── CLOUD-LLM-ARCHITECTURE.md      # Cloud connection, security, cost/cache tracking
├── debugging/                     # Debugging guides by subsystem
├── evaluations/                   # Conversation evaluation reports (v1→v7)
├── guides/                        # How-to guides
├── standards/
│   ├── coding-style.md            # Language-agnostic conventions
│   └── documentation.md           # Doc structure rules
├── technical/                     # Technical implementation notes
├── archive/                       # Archived/superseded documents
└── changes/                       # Per-feature edit history
    └── <change-slug>/
        └── CHANGELOG.md           # Mandatory entry per implementation task
```

## Key Resources Outside docs/

| Path | Purpose |
|------|---------|
| `AGENTS.md` | Agent entry point — SDD workflow summary |
| `.cursorplan/` | Persisted Cursor plans |
| `.cursor/rules/` | Enforced SDD rules |
| `.cursor/skills/sdd-kiro-hitl/` | HITL popup scripts |
| `.cursor/commands/` | `/sdd-init`, `/sdd-status`, `/sdd-verify` |
| `specs/memory/constitution.md` | Non-negotiable constraints |
| `specs/memory/verification.md` | Test contract |
| `specs/templates/` | Fill-in templates |
| `specs/active/` | In-progress changes |
| `specs/completed/` | Archived changes |

## SDD Workflow Quick Reference

See [`AGENTS.md`](../AGENTS.md) for the full workflow. Summary:

1. Start in **Plan** mode — no product code
2. `/sdd-init <slug>` → scaffolds change
3. Write `requirements.md` → AskQuestion popup → approve
4. Write `design.md` → AskQuestion popup → approve
5. Write `tasks.md` → AskQuestion popup → approve
6. Switch to **Agent** mode → AskQuestion implement popup → approve
7. Implement one task at a time: CHANGELOG → verify → popup
8. All tasks done: `verification-report.md` → feature-verify popup → archive

## Related

- [Enhancing Cursor's Agentic Mode.md](../Enhancing%20Cursor's%20Agentic%20Mode.md) — research rationale
- [`AGENTS.md`](../AGENTS.md) — agent workflow
- [`docs/INDEX.md`](INDEX.md) — machine manifest

## Last updated

2026-06-07 — DeepSeek V4 architecture docs; CLOUD-LLM rewrite; dev-startup `.env.local`
