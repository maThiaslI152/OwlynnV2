# CHANGELOG: fix-reconnect-progress-loss

> **Change:** Fix reconnect task progress loss when deepseek-cursor-proxy disconnects.

## [Task 1] 2026-05-31T05:05:00Z
**Type:** feature
**Spec:** AC-1, AC-4, AC-5
**Summary:** Enhanced sdd-session.sh to inject completed task summary and next pending task number into session start context, enabling the agent to resume where it left off after a disconnect.
### Files
- `.cursor/hooks/sdd-session.sh` — added verification.tasks parsing, task progress table, resume instruction in system_prompt
### Notes
- No-op when no tasks are completed (no regression)
- Conditionally includes task progress section only when data exists

## [Task 2] 2026-05-31T05:07:00Z
**Type:** feature
**Spec:** AC-2, AC-3
**Summary:** Added "Resume on Reconnect" rule section to sdd-agent-mode.mdc instructing the agent to check state.json.verification.tasks before implementing and skip completed tasks.
### Files
- `.cursor/rules/sdd-agent-mode.mdc` — new "Resume on Reconnect" section before Per-Task Protocol
### Notes
- Agent announces "Tasks X-Y already done. Resuming at task Z."

## [Task 3] 2026-05-31T05:08:00Z
**Type:** feature
**Spec:** AC-4
**Summary:** Added resume annotation to sdd-core.mdc Per-Task Protocol section and Session Start section.
### Files
- `.cursor/rules/sdd-core.mdc` — resume instruction in Per-Task Protocol + Session Start
### Notes
- Minimal addition — one line in each section
