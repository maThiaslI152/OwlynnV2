import os
import ast

def extract_functions(source_path, target_path, function_names):
    with open(source_path, 'r') as f:
        source = f.read()
    
    tree = ast.parse(source)
    extracted = []
    
    # We need to keep imports. We'll grab all import statements.
    imports = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.append(ast.get_source_segment(source, node))
            
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in function_names:
            extracted.append(ast.get_source_segment(source, node))
            
    with open(target_path, 'w') as f:
        f.write("\n".join(imports) + "\n\n" + "\n\n".join(extracted) + "\n")

# Target functions for fallback
fallback_funcs = ["_fallback_for_blank_response"]
# Target functions for formatter
formatter_funcs = [
    "_strip_thinking_tags",
    "_flatten_human_content", 
    "_synthetic_answer_from_web_search_tool"
]

extract_functions("src/agent/nodes/complex.py", "src/agent/nodes/complex_utils/fallback.py", fallback_funcs)
extract_functions("src/agent/nodes/complex.py", "src/agent/nodes/complex_utils/formatter.py", formatter_funcs)

print("Extraction complete")
