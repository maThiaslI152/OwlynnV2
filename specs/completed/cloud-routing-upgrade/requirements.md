# Requirements

## 1. User Story
As a user of Owlynn on an M4 Mac, I want the system to cleanly and safely route complex reasoning tasks to DeepSeek V4 while preventing errors from image uploads, avoiding unnecessary local model swapping, and fully utilizing the massive 1M token context window of the cloud model. Furthermore, I want to ensure my PII and API keys are completely stripped via robust anonymization before any text leaves my machine.

## 2. Context & Problem Statement
Currently, the multi-LLM routing architecture has several bottlenecks:
- `complex.py` enforces a hardcoded 16K context limit, ignoring DeepSeek V4's 1M context capacity.
- The `selector.py` handles model swapping for `complex-vision` and `complex-longctx`, which are now obsolete since the primary local `complex-default` Qwen model handles both natively.
- DeepSeek V4 does not support image inputs, leading to fatal crashes if a user's task includes images but is escalated to the cloud.
- The `anonymization.py` engine strips generic tokens but entirely misses AWS Access Keys (AKIA), IPv6 addresses, and leaves standard Unix system paths exposed (like `/etc/passwd`).

## 3. Core Requirements
- **FR-1:** **Dynamic Context Windows:** Context limits must dynamically match the active route's configured limit (`1,048,576` for `cloud`), instead of a static `16384`.
- **FR-2:** **Vision Fallback Guard:** If `complex-cloud` is selected but `features.has_images` is true, the route must gracefully downgrade to `complex-default`.
- **FR-3:** **Remove Obsolete Routes:** Delete all references and logic for `complex-vision` and `complex-longctx` from `selector.py`, `classifier.py`, and `complex.py`.
- **FR-4:** **Cloud Parameters:** Inject the `extra_body` configuration object to the `ChatOpenAI` client in `llm.py` so the user can freely toggle "Thinking Mode" and effort levels via `defaults.yaml`.
- **FR-5:** **Security Hardening:** Patch `anonymization.py` to scrub AWS Access Keys, IPv6 addresses, Unix system paths (`/var`, `/etc`, `/tmp`, `/opt`), and trim trailing punctuation from matched paths to prevent dirty placeholders.

## 4. Acceptance Criteria
- [ ] `complex_node` allows prompts exceeding 16K to be sent to DeepSeek V4 without truncation.
- [ ] Tasks containing images are never sent to DeepSeek.
- [ ] `defaults.yaml` accurately sets DeepSeek V4 limits to 1M context and supports `extra_body` parameters.
- [ ] LM Studio `SwapManager` is completely removed for `get_medium_llm`.
- [ ] Automated and manual tests confirm AWS keys and IPv6 addresses are properly redacted before reaching the cloud.
