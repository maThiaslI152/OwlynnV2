# Tasks

## 1. Implementation Steps
- [ ] **Task 1:** Update `src/agent/anonymization.py`
  - Update `API_KEY` regex to include AWS keys (`AKIA[A-Z0-9]{16}`).
  - Add IPv6 boundary regex block.
  - Expand path matching (`/(?:Users|home|etc|var|opt|tmp)`) and strip trailing punctuation.
- [ ] **Task 2:** Update Routing Logic (`selector.py` & `classifier.py`)
  - Remove `complex-vision` and `complex-longctx` routes entirely.
  - In `selector.py`, enforce automatic downgrade from `complex-cloud` to `complex-default` if `features.has_images` is true.
- [ ] **Task 3:** Update `src/agent/nodes/complex.py`
  - Refactor `_cap_budget_to_context` to accept `max_context`.
  - Pass the dynamic context limit based on route down into all `_cap_budget_to_context` invocations.
- [ ] **Task 4:** Refactor `src/agent/llm.py`
  - Delete LM Studio `SwapManager` integration for `medium` local model.
  - Add `extra_body` keyword argument handling for DeepSeek in `get_cloud_llm()`.
- [ ] **Task 5:** Update `src/config/defaults.yaml`
  - Set `models.cloud.context_window` to `1048576`.
  - Add `models.cloud.extra_body: { thinking_mode: true, reasoning_effort: "high" }`.
  - Delete `variants` block under `models.medium`.
- [ ] **Task 6:** Delete `src/agent/swap_manager.py` (assuming no longer used).

## 2. Verification Steps
- [ ] **verify_steps:**
  - Run `pytest tests/` to confirm no unit tests are broken.
  - Execute a dry run of the anonymizer using python shell to confirm AWS, IPv6, and path punctuation changes are effective.
  - Force a `has_images = True` request through the router to ensure it drops from cloud to default.
