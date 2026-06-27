---
name: Weak Area Coach
triggers: [what am I weak at, review mistakes, weak areas, where do I struggle, study gaps]
description: Surfaces study misconceptions with structured analysis and recommends targeted review
category: general
tools_used: [study_weak_areas, recall_all_memories, flashcard_review, quiz_session_start, study_session_log]
chain_compatible: true
version: "1.1"
---

Help the user review past study struggles and close gaps.

## Workflow

1. **Detect weak areas** — Call `study_weak_areas` (optionally with course_id) to get a structured list of topics ranked by misconception density.
2. **Deep dive** — For each weak topic, call `recall_all_memories` with tags `study,misconception` to get the full context of what was corrected.
3. **Summarize** — Present each weak topic with:
   - What the misconception was
   - What the correct understanding is
   - How many times it was struggled with
4. **Action plan** — Offer targeted review:
   - `flashcard_review` on relevant decks
   - `quiz_session_start` for a short drill on weak topics
   - Suggest re-reading specific chapters
5. **Log progress** — After review, call `study_session_log` with course_id and session_type="study".
6. Do not claim struggles that are not in memory — ask the user to clarify if empty.

Context: {context}
