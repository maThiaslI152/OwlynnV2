source_path = "src/api/server.py"
with open(source_path, "r") as f:
    lines = f.readlines()

new_imports = """
from src.api.routes import profile, settings, memory, project, files, openai
from src.api.ws import handler as ws_handler
"""

new_includes = """
app.include_router(profile.router)
app.include_router(settings.router)
app.include_router(memory.router)
app.include_router(project.router)
app.include_router(files.router)
app.include_router(openai.router)
app.include_router(ws_handler.router)
"""

for i, line in enumerate(lines):
    if line.startswith("app = FastAPI("):
        lines.insert(i + 1, new_includes)
        break

for i, line in enumerate(lines):
    if line.startswith("from fastapi import FastAPI"):
        lines.insert(i, new_imports)
        break

with open(source_path, "w") as f:
    f.writelines(lines)

print("Injected routers into server.py")
