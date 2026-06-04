# Plan: Owlynn Conversation Evaluation

> **Purpose:** Canonical implementation plan. Manual browser-based evaluation of Owlynn's conversation quality.

## Summary

Conduct a real browser-based conversation with Owlynn across 5 curated topics in a single chat session of ~25+ exchanges. Score every response against an 8-category 1-5 numeric rubric. Produce a verification report (SDD artifact) and a standalone evaluation document.

## Strategy

This is a **pure evaluation** — no product code changes. The agent acts as both tester and evaluator:
1. Launch Owlynn locally using the `run-user-test` skill
2. Use Cursor IDE browser MCP tools to interact with the chat UI
3. Follow a strict message protocol across 5 topics
4. Capture screenshots at key transitions
5. Score all responses post-session
6. Generate dual-format reports

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| Single continuous chat | Tests topic-shift handling and context retention within one context window |
| Agent-curated topics | Systematic coverage of different agent capabilities (knowledge, code, creative, continuity, search) |
| 8-category 1-5 rubric | Quantifiable, evidence-backed, comparable across runs |
| Dual report artifacts | SDD compliance + shareable standalone doc |

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| LM Studio not running | Medium | High (no LLM responses) | Verify before starting; prompt user to open LM Studio |
| Owlynn responses timeout | Medium | Medium | 120s timeout; score C1=1, C6=1, continue |
| No HITL events trigger | Medium | Low | Score C4/C5 as N/A; note as limitation |
| Browser tab crashes | Low | Medium | Reload and resume from last completed topic |
| Conversation exceeds context window | Low | Medium | Monitor for degradation; note in report if observed |

## Timeline / Effort Estimate

- Setup: ~5 min (launch services, verify)
- Test execution: ~25-35 min (sending messages, waiting for responses)
- Scoring: ~15-20 min (review excerpts, apply rubric)
- Report generation: ~15-20 min
- **Total: ~60-80 min**

## Open Questions

- [ ] None — all parameters clarified during intent-clarification and requirements-review

## Last Updated

2026-06-02 — tasks approved, ready for implement-review
