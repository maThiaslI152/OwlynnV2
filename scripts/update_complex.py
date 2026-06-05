import ast
import os

source_path = "src/agent/nodes/complex.py"
with open(source_path, 'r') as f:
    source = f.read()

tree = ast.parse(source)

funcs_to_remove = [
    "_fallback_for_blank_response",
    "_strip_thinking_tags",
    "_flatten_human_content", 
    "_synthetic_answer_from_web_search_tool"
]

class RemoveFuncs(ast.NodeTransformer):
    def visit_FunctionDef(self, node):
        if node.name in funcs_to_remove:
            return None
        return node

new_tree = RemoveFuncs().visit(tree)
new_code = ast.unparse(new_tree)

# Prepend the new imports
new_imports = """
from .complex_utils.fallback import _fallback_for_blank_response
from .complex_utils.formatter import (
    _strip_thinking_tags,
    _flatten_human_content,
    _synthetic_answer_from_web_search_tool
)
"""

with open(source_path, 'w') as f:
    f.write(new_imports + "\n" + new_code)
print("complex.py updated")
