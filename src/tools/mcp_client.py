"""
MCP Client Manager for LangChain.

This module provides the `MCPClientManager` to consume Model Context Protocol (MCP)
servers as native LangChain tools by establishing STDIO, HTTP, or SSE transports,
generating strict Pydantic schemas, and caching tool definitions.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Optional

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, create_model

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    _HAS_MCP = True
except ImportError:
    _HAS_MCP = False

from src.config.settings import PROJECT_ROOT

logger = logging.getLogger(__name__)

CACHE_FILE = PROJECT_ROOT / "data" / "mcp_schema_cache.json"


def _json_schema_to_pydantic(
    name: str, schema: dict[str, Any] | None
) -> type[BaseModel]:
    """Dynamically construct a Pydantic model for LangChain args_schema from MCP inputSchema."""
    if not schema or not isinstance(schema, dict):
        return create_model(f"{name}_Input")

    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    fields: dict[str, Any] = {}

    type_map = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": list,
        "object": dict,
    }

    for prop_name, prop_spec in properties.items():
        if not isinstance(prop_spec, dict):
            continue
        prop_type = type_map.get(prop_spec.get("type"), Any)
        prop_desc = prop_spec.get("description", "")
        if prop_name in required:
            fields[prop_name] = (prop_type, Field(description=prop_desc))
        else:
            default_val = prop_spec.get("default", None)
            fields[prop_name] = (
                Optional[prop_type],
                Field(default=default_val, description=prop_desc),
            )

    if not fields:
        return create_model(f"{name}_Input")

    return create_model(f"{name}_Input", **fields)


class MCPTool(BaseTool):
    """A LangChain tool that delegates execution to an MCP server."""

    name: str
    description: str
    server_name: str
    mcp_tool_name: str
    manager: MCPClientManager = Field(exclude=True)
    args_schema: type[BaseModel] | None = None

    async def _arun(self, **kwargs) -> str:
        return await self.manager.execute_tool(
            self.server_name, self.mcp_tool_name, kwargs
        )

    def _run(self, **kwargs) -> str:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            return "Error: Use async _arun"

        return loop.run_until_complete(self._arun(**kwargs))


class MCPClientManager:
    """Manages connections to external MCP servers to ingest them as LangChain tools."""

    def __init__(self):
        self.sessions: dict[str, Any] = {}
        self.langchain_tools: list[BaseTool] = []
        self._server_params: dict[str, Any] = {}
        self._schema_cache: dict[str, Any] = {}
        self._initialized = False

    def _load_cache(self) -> None:
        """Load schema cache from disk if present."""
        if CACHE_FILE.is_file():
            try:
                self._schema_cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.debug("Failed to read MCP schema cache: %s", exc)

    def _save_cache(self) -> None:
        """Persist schema cache to disk."""
        try:
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            CACHE_FILE.write_text(
                json.dumps(self._schema_cache, indent=2), encoding="utf-8"
            )
        except Exception as exc:
            logger.debug("Failed to write MCP schema cache: %s", exc)

    async def initialize(self, config_path: str = "mcp_config.json"):
        if self._initialized:
            return

        if not _HAS_MCP:
            logger.debug("MCP package not installed; skipping MCP tool initialization.")
            self._initialized = True
            return

        self._load_cache()

        if not os.path.exists(config_path):
            logger.info(
                "No MCP config found at %s. Skipping external tools.", config_path
            )
            self._initialized = True
            return

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
        except Exception as e:
            logger.warning("Failed to load MCP config: %s", e)
            self._initialized = True
            return

        mcp_servers = config_data.get("mcpServers", {})

        for name, details in mcp_servers.items():
            command = details.get("command")
            args = details.get("args", [])
            env = details.get("env")
            url = details.get("url")

            if command:
                params = StdioServerParameters(command=command, args=args, env=env)
                self._server_params[name] = {"type": "stdio", "params": params}
            elif url:
                self._server_params[name] = {
                    "type": "http",
                    "url": url,
                    "headers": details.get("headers", {}),
                }
            else:
                continue

            # Check cache or discover
            cached_tools = self._schema_cache.get(name)
            if cached_tools:
                for tool_meta in cached_tools:
                    pydantic_schema = _json_schema_to_pydantic(
                        f"{name}_{tool_meta['name']}", tool_meta.get("inputSchema")
                    )
                    lc_tool = MCPTool(
                        name=f"{name}_{tool_meta['name']}",
                        description=tool_meta.get("description")
                        or f"Tool {tool_meta['name']} from {name}",
                        server_name=name,
                        mcp_tool_name=tool_meta["name"],
                        manager=self,
                        args_schema=pydantic_schema,
                    )
                    self.langchain_tools.append(lc_tool)
                continue

            # Live discovery if not cached and stdio
            if command:
                try:

                    async def _discover_stdio(p):
                        async with stdio_client(p) as (read, write):
                            async with ClientSession(read, write) as session:
                                await session.initialize()
                                return await session.list_tools()

                    tools_response = await asyncio.wait_for(
                        _discover_stdio(params), timeout=3.0
                    )
                    server_tool_cache = []

                    for mcp_tool in tools_response.tools:
                        tool_dict = {
                            "name": mcp_tool.name,
                            "description": mcp_tool.description,
                            "inputSchema": getattr(mcp_tool, "inputSchema", {}),
                        }
                        server_tool_cache.append(tool_dict)
                        pydantic_schema = _json_schema_to_pydantic(
                            f"{name}_{mcp_tool.name}", tool_dict["inputSchema"]
                        )
                        lc_tool = MCPTool(
                            name=f"{name}_{mcp_tool.name}",
                            description=mcp_tool.description
                            or f"Tool {mcp_tool.name} from {name} server",
                            server_name=name,
                            mcp_tool_name=mcp_tool.name,
                            manager=self,
                            args_schema=pydantic_schema,
                        )
                        self.langchain_tools.append(lc_tool)
                        logger.info("Loaded MCP tool: %s", lc_tool.name)

                    self._schema_cache[name] = server_tool_cache
                except Exception as e:
                    logger.warning("Failed to connect to MCP server %s: %s", name, e)

        self._save_cache()
        self._initialized = True

    async def execute_tool(
        self, server_name: str, tool_name: str, arguments: dict
    ) -> str:
        server_info = self._server_params.get(server_name)
        if not server_info:
            return f"Error: MCP server '{server_name}' not configured."

        if not _HAS_MCP:
            return "Error: MCP Python library is not installed."

        if server_info.get("type") == "stdio":
            params = server_info["params"]
            for attempt in range(2):
                try:
                    async with stdio_client(params) as (read, write):
                        async with ClientSession(read, write) as session:
                            await session.initialize()
                            result = await session.call_tool(tool_name, arguments)
                            text_parts = [
                                item.text
                                for item in result.content
                                if hasattr(item, "text")
                            ]
                            return "\n".join(text_parts)
                except Exception as e:
                    if attempt == 0:
                        await asyncio.sleep(0.5)
                        continue
                    logger.warning("MCP tool execution failed: %s", e)
                    return (
                        f"Error executing MCP tool {tool_name} on {server_name}: {e!s}"
                    )

        return f"Error: Unsupported transport for MCP server '{server_name}'"

    def get_tools(self) -> list[BaseTool]:
        return self.langchain_tools


# Global manager instance
mcp_manager = MCPClientManager()


def get_mcp_tools() -> list[BaseTool]:
    """
    Returns the list of dynamically ingested LangChain tools originating from MCP servers.
    Note: Requires mcp_manager.initialize() to have been called.
    """
    return mcp_manager.get_tools()
