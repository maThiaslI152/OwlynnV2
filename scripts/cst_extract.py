import libcst as cst

source_path = "src/api/server.py"
with open(source_path, "r") as f:
    source_code = f.read()

module = cst.parse_module(source_code)

# We want to identify the decorators and extract the function.
# Let's map prefixes to router files.
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


class RouteExtractor(cst.CSTVisitor):
    def __init__(self):
        self.routes = {}  # file -> list of function nodes
        self.nodes_to_remove = set()

    def visit_FunctionDef(self, node: cst.FunctionDef):
        # check decorators
        for dec in node.decorators:
            if isinstance(dec.decorator, cst.Call):
                func = dec.decorator.func
                if (
                    isinstance(func, cst.Attribute)
                    and getattr(func.value, "value", "") == "app"
                ):
                    method = func.attr.value
                    if method in ["get", "post", "put", "delete", "websocket"]:
                        # get the path
                        path_arg = dec.decorator.args[0].value
                        if isinstance(path_arg, cst.SimpleString):
                            path = path_arg.value.strip("\"'")
                            # determine target file
                            target_file = None
                            for prefix, file in ROUTE_MAP.items():
                                if path.startswith(prefix):
                                    target_file = file
                                    break

                            if target_file:
                                if target_file not in self.routes:
                                    self.routes[target_file] = []

                                # Replace @app.get with @router.get
                                new_dec = dec.with_changes(
                                    decorator=dec.decorator.with_changes(
                                        func=func.with_changes(value=cst.Name("router"))
                                    )
                                )
                                # Create new decorators list
                                new_decorators = [
                                    new_dec if d is dec else d for d in node.decorators
                                ]
                                new_node = node.with_changes(decorators=new_decorators)

                                self.routes[target_file].append(new_node)
                                self.nodes_to_remove.add(node)
                                return False
        return True


extractor = RouteExtractor()
module.visit(extractor)

print(f"Extracted routes for {len(extractor.routes)} files.")
for f, nodes in extractor.routes.items():
    print(f"  {f}: {len(nodes)} routes")
