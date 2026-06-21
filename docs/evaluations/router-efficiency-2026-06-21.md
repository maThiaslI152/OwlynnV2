# Evaluation Report: Router Efficiency & Local Model Usage

## 1. Interaction Outcome (Success)
The recent patches to `content_interact.js` and `buildDomTree.js` were highly successful. The agent was able to seamlessly:
- Read the hidden DOM elements and wait for the secret form delay
- Type into the text fields
- Scroll the terms modal and click the "I Accept" button (which correctly synced the checkbox state)
- Interact with the native HTML `<select>` dropdown and choose "Computer Science"
- Proceed to Step 3 and click "Submit Final Answers", triggering the successful hand-off alert.

The automation workflow itself is now robust against complex multi-step forms.

## 2. Router Model Efficiency (Failure)
While the automation succeeded, the **router failed to utilize the local Gemma-4 model**. Every single turn was routed to `large-cloud` (DeepSeek).

**Why did this happen?**
In `src/agent/nodes/router.py`, there is a hardcoded bypass designed to maintain context coherence:
```python
    # If the conversation already used tools or the large model, stay on complex.
    if len(messages) > 2:
        has_tool_history = any(
            getattr(m, "type", None) == "tool"
            or hasattr(m, "tool_calls")
            and m.tool_calls
            for m in messages[:-1]
        )
        if has_tool_history:
            logger.info("[router] Complex path — conversation has tool history")
            # Forces route to complex-cloud
```
Because you ran this prompt in a chat thread that *already* had previous tool usage (from when it got stuck earlier), the router saw the history and instantly bypassed the LLM classification, forcing the entire interaction onto the expensive cloud model.

## 3. Overall Performance & Token Usage
Because the interaction was pushed to the cloud, token usage was extremely high. Looking at the server logs, the context window grew continuously with each DOM tree read:
- Turn 1: ~11,358 tokens
- Turn 5: ~13,405 tokens
- Turn 9: ~17,658 tokens

This completely undermines the goal of using the local model for DOM token compression.

## 4. Recommendations for Improvement
To achieve your goal of zero-token-cost local browser automation, we must patch `src/agent/nodes/router.py`.

**Proposed Fix:**
We need to add a fast-path bypass *before* the `has_tool_history` check. The Owlynn Browser Extension automatically injects a specific system note into the prompt:
`[SYSTEM NOTE: This context was sent directly from the active browser tab via the Owlynn Browser Extension...]`

We should update the router so that if `user_text` contains this system note, it immediately routes to `browser_local`, completely ignoring any previous tool history in the thread.
