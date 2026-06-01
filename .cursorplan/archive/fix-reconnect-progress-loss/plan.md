# Plan: fix-reconnect-progress-loss

## Linked specs
- specs/active/fix-reconnect-progress-loss/requirements.md
- specs/active/fix-reconnect-progress-loss/design.md
- specs/active/fix-reconnect-progress-loss/tasks.md

## Summary
Prevent the SDD agent from losing task progress when deepseek-cursor-proxy disconnects. After reconnect, the agent resumes from the first incomplete task instead of restarting from task 1. Three-layer defense: session hook context injection, rule-based auto-skip, and state.json tracking.

## Scope (in / out)
**In scope:**
- sdd-session.sh: inject completed task summary + next pending task
- sdd-agent-mode.mdc: "Resume on Reconnect" rule block
- sdd-core.mdc: resume annotation in Per-Task Protocol

**Out of scope:**
- Full conversation history persistence
- Proxy-level fixes
- Cross-machine resumption
- Partial-task detection

## Architecture decisions
- Trust state.json.verification.tasks as source of truth (already canonical)
- Inject via additional_context (sessionStart hook design)
- No new files — minimal surface area

## Task sequence (high level)
1. Enhance sdd-session.sh with task progress injection
2. Add resume-on-reconnect rules to sdd-agent-mode.mdc
3. Add resume protocol to sdd-core.mdc

## Risks and open questions
- state.json corruption → handled gracefully (fall back to normal start)
- No partial-task detection in v1 (add later if needed)

## Approval history
- requirements-review: approved 2026-05-31
- design-review: approved 2026-05-31
- tasks-review: approved 2026-05-31
