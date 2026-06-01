---
status: active
category: changelog
last_updated: 2026-05-31
owner: human
---

# Progress Report — 2026-05-26

> **Purpose:** Progress report documenting recent fixes and improvements.

## Session Summary

Four changes completed and verified end-to-end:

1. **HITL "no context" false-positive fix** — `src/tools/skills.py`
2. **Chat markdown rendering** — `frontend-v2/` (react-markdown + remark-gfm + rehype-raw + rehype-sanitize)
3. **HITL gate skill-match override** — `src/agent/nodes/router.py` (confident skill matches bypass HITL even when LLM router confidence is low)
4. **GFM table rendering verified** — 1 table rendered as `<table class="msg-table">` with proper CSS in live end-to-end test

---

## Completed Fixes

### 1. HITL "No Context" False-Positive Fix

**File**: `src/tools/skills.py`

| Change | Before | After |
|---|---|---|
| `vague_query` detection (line 399-401) | `OR`: short OR no-intent-keywords | `AND`: short AND no-intent-keywords |
| No-match handling (lines 415-421) | Always returned `is_ambiguous=True` | Returns `is_ambiguous=False` when query is NOT vague |

**Impact**: Simple questions like "what is 2+2?" or "help me" no longer trigger the 5-option HITL menu. Only truly vague queries (< 3 words, no intent keywords) now trigger HITL. Clear queries with no exact skill match route directly to the LLM.

**Tests**: `tests/test_skill_matcher.py` — updated 3 existing tests, added 2 new tests (`test_substantive_query_no_skill_match_is_not_ambiguous`, `test_empty_skills_clear_query_is_not_ambiguous`). All pass.

### 2. Chat Markdown Rendering Fix

**Problem**: Chat messages displayed raw markdown (tables with `|`, headings, HTML) because the custom parser in `frontend-v2/src/lib/markdown.tsx` only handled bold, inline-code, code-blocks, and links.

**Fix**:

| File | Change |
|---|---|
| `frontend-v2/package.json` | Added `react-markdown ^10.1.0`, `remark-gfm ^4.0.1`, `rehype-raw ^7.0.0`, `rehype-sanitize ^6.0.0` |
| `frontend-v2/src/components/AppShell.tsx` | `MessageContent` component replaced custom `parseMarkdown` with `<ReactMarkdown>` using `remarkGfm` (tables/strikethrough/task-lists), `rehypeRaw` (inline HTML), and `rehypeSanitize` with extended schema allowing `style` on div/span/strong for Visual Comparison HTML card output |
| `frontend-v2/src/index.css` | Added `.msg-table`, `.msg-heading` (h1-h6), `.msg-list`, blockquote, hr, paragraph spacing styles |

---

## Completed Follow-Up Fixes (Verified)

### 3. HITL Gate Skill-Match Override

**File**: `src/agent/nodes/router.py` (lines 417-428)

**Problem**: When the skill matcher found a confident, unambiguous match (e.g., "compare" → Visual Comparison, keyword score 1.0), but the LLM router had low confidence (< 0.6), the OR'd HITL trigger (`confidence < threshold OR is_ambiguous`) forced the generic 5-option menu. The skill match was never presented.

**Fix**: Added an override after the `hitl_needed` computation: when the skill matcher found a confident match (`not is_ambiguous` AND `best_score >= skill_clarification_threshold`), force `hitl_needed = False`. The proactive skill-matching block at lines 539-552 then sets `skill_matched` and overrides the toolbox with skill-specific tools.

```python
if (
    hitl_needed
    and not match_result.is_ambiguous
    and match_result.best_score >= skill_clarification_threshold
):
    hitl_needed = False
```

**Verified**: Sent "Compare React vs Vue for frontend development" through the full pipeline — no HITL interruption, response routed with correct toolbox, Visual Comparison skill applied.

### 4. GFM Table Rendering — Verified

**Verified end-to-end**: Backend on port 8000, frontend on 5173. Sent comparison query. DOM inspection confirmed:

- `1 table found` — rendered as `<table class="msg-table">` with `<th>`, `<td>`, proper CSS (borders, alternating row backgrounds, uppercase headers)
- Headings, lists, links, paragraphs all render with correct CSS classes
- No raw markdown or HTML visible

**Package versions**: react-markdown@10.1.0, remark-gfm@4.0.1, rehype-raw@7.0.0, rehype-sanitize@6.0.0

**Tests**: 34 router/graph tests pass, 36 skill matcher tests pass (2 pre-existing sklearn failures unrelated).

---

## Files Reference

| File | Role |
|---|---|
| `src/tools/skills.py` | Skill definitions, SkillLoader, SkillMatcher (keyword + TF-IDF hybrid matching) |
| `src/agent/nodes/router.py` | Router node with 5-way routing, HITL gating, skill matching integration |
| `src/config/settings.py` | PROJECT_ROOT path, SKILLS_DIR derivation |
| `frontend-v2/src/components/AppShell.tsx` | MessageContent with ReactMarkdown + sanitize schema |
| `frontend-v2/src/index.css` | `.msg-table`, `.msg-heading`, `.msg-list` styles |
| `frontend-v2/src/lib/markdown.tsx` | Old custom parser (no longer used by MessageContent) |
| `frontend-v2/src/components/OrchestrationPanel.tsx` | Inspector panel showing route/confidence/model info |
| `frontend-v2/package.json` | Dependencies: react-markdown, remark-gfm, rehype-raw, rehype-sanitize |
| `skills/visual_comparison.md` | Visual Comparison skill with "compare" trigger |
| `tests/test_skill_matcher.py` | 17 tests covering keyword, semantic, match, confidence, ambiguity |

## Related

- [`docs/STATUS.md`](STATUS.md) — project status
- [`docs/README.md`](README.md) — project documentation map

## Last updated

2026-05-31 — `docs-standards-timeline` added frontmatter, purpose blockquote
