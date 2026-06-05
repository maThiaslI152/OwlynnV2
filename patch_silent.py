import ast
import os
import re

def patch_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()
    
    try:
        tree = ast.parse(source)
    except Exception:
        return
        
    lines = source.splitlines()
    patches_made = 0
    
    # We collect line numbers to patch
    to_patch = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            catches_exception = False
            if node.type is None:
                catches_exception = True # Bare except
            elif isinstance(node.type, ast.Name) and node.type.id == 'Exception':
                catches_exception = True
            
            if catches_exception:
                has_logging = False
                for stmt in ast.walk(node):
                    if isinstance(stmt, ast.Raise):
                        has_logging = True
                    if isinstance(stmt, ast.Call):
                        if isinstance(stmt.func, ast.Name) and stmt.func.id in ('print', 'audit_error', 'audit_warn'):
                            has_logging = True
                        if isinstance(stmt.func, ast.Attribute):
                            if stmt.func.attr in ('error', 'warning', 'exception', 'critical', 'info', 'debug'):
                                has_logging = True
                
                if not has_logging:
                    to_patch.append((node.lineno, node.name))

    if not to_patch:
        return
        
    # Sort backwards so patching doesn't affect previous line numbers
    to_patch.sort(key=lambda x: x[0], reverse=True)
    
    for lineno, as_name in to_patch:
        line_idx = lineno - 1
        line_str = lines[line_idx]
        
        # Determine indentation
        indent = len(line_str) - len(line_str.lstrip())
        indent_str = line_str[:indent]
        inner_indent = indent_str + "    "
        
        if as_name is None:
            # Change "except Exception:" or "except:" to "except Exception as e:"
            if "except Exception:" in line_str:
                lines[line_idx] = line_str.replace("except Exception:", "except Exception as e:")
            elif "except:" in line_str:
                lines[line_idx] = line_str.replace("except:", "except Exception as e:")
            else:
                # E.g. except (ValueError, Exception): - rare but possible
                pass
            as_name = "e"
            
        # Check if the next line is just pass or return
        # Insert logging statement
        log_stmt = inner_indent + f'import logging; logging.debug("Silent error suppressed: %s", {as_name})'
        lines.insert(line_idx + 1, log_stmt)
        patches_made += 1

    if patches_made > 0:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(f"Patched {patches_made} silent swallows in {filepath}")

for root, dirs, files in os.walk("src"):
    for file in files:
        if file.endswith(".py"):
            patch_file(os.path.join(root, file))
