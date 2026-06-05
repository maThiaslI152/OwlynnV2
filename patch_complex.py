import re

with open("src/agent/nodes/complex.py", "r") as f:
    code = f.read()

# 1. Remove _LARGE_CONTEXT_WINDOW definition
code = re.sub(r"_LARGE_CONTEXT_WINDOW = int\(.*?\)\n", "", code, flags=re.DOTALL)

# 2. Update _cap_budget_to_context definition
code = code.replace(
    "def _cap_budget_to_context(prompt_messages: list, requested_budget: int) -> int:",
    "def _cap_budget_to_context(prompt_messages: list, requested_budget: int, max_context: int) -> int:"
)
code = code.replace(
    "available = _LARGE_CONTEXT_WINDOW - input_tokens - _CONTEXT_SAFETY_MARGIN",
    "available = max_context - input_tokens - _CONTEXT_SAFETY_MARGIN"
)

# 3. Update _needs_prompt_truncation
code = code.replace(
    "def _needs_prompt_truncation(prompt_messages: list) -> bool:",
    "def _needs_prompt_truncation(prompt_messages: list, max_context: int) -> bool:"
)
code = code.replace(
    "limit = int(_LARGE_CONTEXT_WINDOW * _HARD_PROMPT_LIMIT_RATIO)",
    "limit = int(max_context * _HARD_PROMPT_LIMIT_RATIO)"
)

# 4. Resolve max_context early in complex_llm_node
res_logic = """    route = state.get("route") or "complex-default"
    if route == "complex-cloud":
        max_context = int(config.get("models.cloud.context_window", 1048576))
    else:
        max_context = int(config.get("models.medium.context_window", 16384))
"""
code = code.replace(
    '    route = state.get("route") or "complex-default"\n    model_label = "medium-default"',
    res_logic + '    model_label = "medium-default"'
)

# 5. Add max_context to all _cap_budget_to_context calls
code = re.sub(
    r"(_cap_budget_to_context\([^,]+,\s*[^)]+)\)",
    r"\1, max_context)",
    code
)

# 6. Remove complex-vision and complex-longctx from complex_llm_node
code = re.sub(r'            elif route == "complex-vision":.*?model_label = "medium-vision"', "", code, flags=re.DOTALL)
code = re.sub(r'            elif route == "complex-longctx":.*?model_label = "medium-longctx"', "", code, flags=re.DOTALL)


with open("src/agent/nodes/complex.py", "w") as f:
    f.write(code)

