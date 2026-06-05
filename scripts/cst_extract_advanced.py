import libcst as cst
import os

source_path = "src/api/server.py"
with open(source_path, "r") as f:
    source_code = f.read()

module = cst.parse_module(source_code)

ROUTE_MAP = {
    "/api/profile": "src/api/routes/profile.py",
    "/api/persona": "src/api/routes/profile.py",
    "/api/system-settings": "src/api/routes/settings.py",
    "/api/memory-settings": "src/api/routes/settings.py",
    "/api/advanced-settings": "src/api/routes/settings.py",
    "/api/unified-settings": "src/api/routes/settings.py",
    "/api/memories": "src/api/routes/memory.py",
    "/api/mem0": "src/api/routes/memory.py",
    "/api/topics": "src/api/routes/project.py",
    "/api/interests": "src/api/routes/project.py",
    "/api/conversations": "src/api/routes/project.py",
    "/api/chats": "src/api/routes/project.py",
    "/api/projects": "src/api/routes/project.py",
    "/api/history": "src/api/routes/project.py",
    "/api/tools": "src/api/routes/files.py",
    "/api/artifacts": "src/api/routes/files.py",
    "/api/files": "src/api/routes/files.py",
    "/api/upload": "src/api/routes/files.py",
    "/api/folders": "src/api/routes/files.py",
    "/v1/chat": "src/api/routes/openai.py",
    "/ws/chat": "src/api/ws/handler.py",
}

HELPER_MAP = {
    "extract_pdf_text": "src/api/routes/files.py",
    "render_pdf_as_composite": "src/api/routes/files.py",
    "extract_text_file": "src/api/routes/files.py",
    "notify_file_processed": "src/api/routes/files.py",
    "GraphSession": "src/api/ws/handler.py",
    "serialize_message": "src/api/ws/handler.py",
    "serialize_interrupt_item": "src/api/ws/handler.py",
    "_stringify_tool_input": "src/api/ws/handler.py",
    "_tool_status_from_content": "src/api/ws/handler.py",
    "_tool_risk_metadata": "src/api/ws/handler.py",
    "_stringify_lc_message_content": "src/api/ws/handler.py",
}


class AdvancedExtractor(cst.CSTVisitor):
    def __init__(self):
        self.routes = {f: [] for f in set(ROUTE_MAP.values())}
        self.helpers = {f: [] for f in set(ROUTE_MAP.values())}
        self.imports = []
        self.nodes_to_remove = set()

    def visit_Import(self, node):
        self.imports.append(node)

    def visit_ImportFrom(self, node):
        self.imports.append(node)

    def visit_ClassDef(self, node):
        if node.name.value in HELPER_MAP:
            target = HELPER_MAP[node.name.value]
            self.helpers[target].append(node)
            self.nodes_to_remove.add(node)

    def visit_FunctionDef(self, node: cst.FunctionDef):
        # Check if it's a helper
        if node.name.value in HELPER_MAP:
            target = HELPER_MAP[node.name.value]
            self.helpers[target].append(node)
            self.nodes_to_remove.add(node)
            return False

        # check decorators for routes
        is_route = False
        for dec in node.decorators:
            if isinstance(dec.decorator, cst.Call):
                func = dec.decorator.func
                if (
                    isinstance(func, cst.Attribute)
                    and getattr(func.value, "value", "") == "app"
                ):
                    method = func.attr.value
                    if method in ["get", "post", "put", "delete", "websocket"]:
                        path_arg = dec.decorator.args[0].value
                        if isinstance(path_arg, cst.SimpleString):
                            path = path_arg.value.strip("\"'")
                            target_file = None
                            for prefix, file in ROUTE_MAP.items():
                                if path.startswith(prefix):
                                    target_file = file
                                    break

                            if target_file:
                                new_dec = dec.with_changes(
                                    decorator=dec.decorator.with_changes(
                                        func=func.with_changes(value=cst.Name("router"))
                                    )
                                )
                                new_decorators = [
                                    new_dec if d is dec else d for d in node.decorators
                                ]
                                new_node = node.with_changes(decorators=new_decorators)

                                self.routes[target_file].append(new_node)
                                self.nodes_to_remove.add(node)
                                is_route = True
                                break
        return not is_route


extractor = AdvancedExtractor()
module.visit(extractor)

# Create the router files
for target_file in extractor.routes.keys():
    os.makedirs(os.path.dirname(target_file), exist_ok=True)
    with open(target_file, "w") as f:
        # Write all imports
        f.write("from fastapi import APIRouter\n")
        f.write("router = APIRouter()\n")
        for imp in extractor.imports:
            f.write(cst.Module([]).code_for_node(imp) + "\n")
        f.write("\n")

        # Write helpers
        for helper in extractor.helpers[target_file]:
            f.write(cst.Module([]).code_for_node(helper) + "\n\n")

        # Write routes
        for route in extractor.routes[target_file]:
            f.write(cst.Module([]).code_for_node(route) + "\n\n")

print(f"Extracted routes to {len(extractor.routes)} files.")


# Now we need to remove them from server.py
class ServerTransformer(cst.CSTTransformer):
    def leave_FunctionDef(self, original_node, updated_node):
        if original_node in extractor.nodes_to_remove:
            return cst.RemoveFromParent()
        return updated_node

    def leave_ClassDef(self, original_node, updated_node):
        if original_node in extractor.nodes_to_remove:
            return cst.RemoveFromParent()
        return updated_node


transformer = ServerTransformer()
modified_module = module.visit(transformer)

with open(source_path, "w") as f:
    f.write(modified_module.code)

print("Removed extracted nodes from server.py.")
