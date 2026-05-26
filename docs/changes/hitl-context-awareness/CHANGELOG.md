# Changelog: hitl-context-awareness

## 2026-06-01 — Initial scaffolding

- Created SDD skeleton for context-aware HITL prompts change

## 2026-06-01 — Tasks 1–3: Implementation

- **Task 1:** Wired `enrich_interrupt()` into `security_proxy.py` with dynamic `_build_title()` and `_build_reason()` helpers; title now shows tool name + primary arg (e.g. "Approve write to file: report.txt?"); tool_args included in payload
- **Task 2:** Updated `HitlPromptCard.tsx` to render `conversationSnippet` (collapsible `<details>`) in all 4 HITL variants; added `ToolArgsTable` component for security_approval and plan_review; added `AffectedResources` list component; added CSS for new elements in `hitl-cards.css`
- **Task 3:** Improved `stated_intent` in `context.py` — replaced weak "Owlynn wants to {last_AI_content}" with tool-aware `_build_intent_from_tool_calls()` that maps tool names to human-readable actions (e.g. "Owlynn wants to write to file /tmp/test.txt")
