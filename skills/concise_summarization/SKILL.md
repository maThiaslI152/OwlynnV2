---
name: concise_summarization
category: writing
description: Procedural skill synthesized from user workflow
triggers: [concise_summarization]
version: '1.0'
---
When asked to summarize a branch or topic in one sentence, strip away the meta-commentary and list only the core subject matter (e.g., 'This conversation tracks Python 3.14 features — free threading, template strings — and compares performance across versions with matplotlib'). Avoid phrases like 'I can explain' or 'Let me summarize'.

## Learned Pitfalls & Workarounds
- # Concise Summarization
When asked for a brief explanation or summary, provide it in the requested format (e.g., one sentence) rather than defaulting to full detail. The user's explicit brevity constraint overrides the default verbosity of long-form explanations.

**Example:** User: "Briefly explain what this branch is about in one sentence." -> Answer: "This branch tracks Python 3.14 features and compares version performance with a matplotlib chart."