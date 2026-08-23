import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.config.settings import MCP_CONFIG_PATH
from src.tools.mcp_client import get_mcp_tools, mcp_manager


async def main():
    print(f"Loading config from: {MCP_CONFIG_PATH}")
    if not os.path.exists(str(MCP_CONFIG_PATH)):
        print("Config file does not exist!")
        return

    await mcp_manager.initialize(str(MCP_CONFIG_PATH))
    tools = get_mcp_tools()
    print(f"Loaded {len(tools)} tools:")
    for t in tools:
        print(f" - {t.name}")


if __name__ == "__main__":
    asyncio.run(main())
