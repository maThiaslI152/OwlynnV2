# Interactive block templates (agent reference)

Use `render_interactive_block(block_type, payload)` to produce fenced markdown for inline chat widgets.

| block_type | Fence lang | Use when |
|------------|------------|----------|
| quiz | owlynn-quiz | Check-for-understanding, mock exam questions |
| steps | owlynn-steps | Multi-step explanations, reveal-one-at-a-time |
| callout | owlynn-callout | Tips, warnings, key notes |
| embed | owlynn-embed | Inline chart/image after notebook_run |
| cell | owlynn-cell | Runnable Python snippet in chat |

For diagrams, emit a ` ```mermaid ` fence directly (no tool required).

Keep assistant prose to 1–3 sentences around each widget.
