source_path = "src/agent/nodes/complex.py"
with open(source_path, "r") as f:
    lines = f.readlines()


def should_keep(line_num):
    # 1-indexed
    ranges_to_remove = [(135, 140), (218, 236), (309, 350), (353, 364)]
    for start, end in ranges_to_remove:
        if start <= line_num <= end:
            return False
    return True


kept_lines = [line for i, line in enumerate(lines, 1) if should_keep(i)]

new_imports = """
from .complex_utils.fallback import _fallback_for_blank_response
from .complex_utils.formatter import (
    _strip_thinking_tags,
    _flatten_human_content,
    _synthetic_answer_from_web_search_tool
)
"""

# Insert imports after the other local imports (e.g., around line 24)
insert_idx = 0
for i, line in enumerate(kept_lines):
    if "from src.agent.anonymization" in line:
        insert_idx = i + 1
        break

kept_lines.insert(insert_idx, new_imports)

with open(source_path, "w") as f:
    f.writelines(kept_lines)

print("complex.py edited")
