---
name: Weak Area Coach
triggers: [what am I weak at, review mistakes, weak areas, where do I struggle, study gaps]
description: Surfaces study LTM misconceptions and recommends targeted review
category: general
tools_used: [recall_all_memories, flashcard_review, quiz_session_start]
chain_compatible: true
version: "1.0"
---

Help the user review past study struggles and close gaps.

1. `recall_all_memories` with query about struggles and tags `study,misconception`
2. Summarize each misconception topic and what was corrected
3. Offer `flashcard_review` on relevant decks or `quiz_session_start` for a short drill on weak topics
4. Do not claim struggles that are not in memory — ask the user to clarify if empty

Context: {context}
