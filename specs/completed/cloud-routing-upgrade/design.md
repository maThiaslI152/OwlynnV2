# Design

## 1. System Architecture
We are modifying the core routing logic inside `src/agent/router/`, simplifying local LLM initialization inside `src/agent/llm.py`, dynamically resolving token boundaries inside `src/agent/nodes/complex.py`, and extending the regex boundary filters inside `src/agent/anonymization.py`.

## 2. Component Design

### 2.1 Anonymization Engine (`src/agent/anonymization.py`)
- **API Keys**: Modify the regex `API_KEY` pattern to explicitly catch `AKIA[A-Z0-9]{16}`.
- **IPv6**: Expand the `IP` regex to catch groups separated by colons (ignoring `::1`).
- **Paths**: Expand `PATH` to match standard Unix prefixes: `/(?:Users|home|etc|var|opt|tmp)`. Use a trailing `(?!\W)` negative lookahead to exclude trailing punctuation.

### 2.2 Route Classifier (`src/agent/router/classifier.py`)
- Remove routes `complex-vision` and `complex-longctx` from the LLM prompt.
- Retain only `simple`, `complex-default`, and `complex-cloud`.

### 2.3 Route Selector (`src/agent/router/selector.py`)
- Remove the `_downgrade_cloud_route` variant fallbacks.
- Remove `_try_keep_current` swap avoidance logic.
- Add an exact match trap: `if target_route == "complex-cloud" and features.has_images: return "complex-default", toolbox`.

### 2.4 Complex Node Execution (`src/agent/nodes/complex.py`)
- Erase the constant `_LARGE_CONTEXT_WINDOW`.
- Update `_cap_budget_to_context` to `_cap_budget_to_context(prompt_messages, requested_budget, max_context)`.
- Determine `max_context` by inspecting `route` and querying the appropriate config path (`models.cloud.context_window` vs `models.medium.context_window`).
- Pass the resolved `max_context` down to all nested calls.

### 2.5 LLM Initialization (`src/agent/llm.py`)
- Remove `SwapManager` entirely from `get_medium_llm`. It simply loads `complex-default`.
- In `get_cloud_llm`, map `model_cfg.get("extra_body")` to the kwargs for `ChatOpenAI`.

## 3. Configuration Updates (`defaults.yaml`)
- Drop `variants.vision` and `variants.longctx`.
- Bump `models.cloud.context_window` to `1048576`.
- Add `models.cloud.extra_body: { thinking_mode: true, reasoning_effort: "high" }`.

## 4. Risks and Mitigations
- **Risk:** IPv6 regex could incorrectly match MAC addresses or timestamps.
- **Mitigation:** Ensure standard IP boundary checks are enforced.
- **Risk:** Dropping SwapManager could break testing or edge cases expecting explicit vision models.
- **Mitigation:** Since `complex-default` natively handles images now, no functionality is lost. The system becomes significantly simpler.
