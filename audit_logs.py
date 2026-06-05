import ast
import os

def check_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()
    
    try:
        tree = ast.parse(source)
    except Exception:
        return
        
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            # Check if it catches Exception
            catches_exception = False
            if node.type is None:
                catches_exception = True # Bare except
            elif isinstance(node.type, ast.Name) and node.type.id == 'Exception':
                catches_exception = True
            
            if catches_exception:
                # Check body for any logging, print, or raise
                has_logging = False
                for stmt in ast.walk(node):
                    if isinstance(stmt, ast.Raise):
                        has_logging = True
                    if isinstance(stmt, ast.Call):
                        if isinstance(stmt.func, ast.Name) and stmt.func.id in ('print', 'audit_error', 'audit_warn'):
                            has_logging = True
                        if isinstance(stmt.func, ast.Attribute):
                            if stmt.func.attr in ('error', 'warning', 'exception', 'critical'):
                                has_logging = True
                
                if not has_logging:
                    print(f"{filepath}:{node.lineno} - Silent swallow")

for root, dirs, files in os.walk("src"):
    for file in files:
        if file.endswith(".py"):
            check_file(os.path.join(root, file))
