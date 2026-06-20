import asyncio
from src.agent.tool_sets import resolve_tools

tools = resolve_tools(["screen_assist"], web_search_enabled=True)
print([t.name for t in tools])
