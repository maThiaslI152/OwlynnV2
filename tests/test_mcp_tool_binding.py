"""MCP extension tools merged into resolve_tools and HITL policy."""

import sys
from unittest.mock import MagicMock, patch

import pytest

sys.modules["mem0"] = MagicMock()

from langchain_core.tools import tool

from src.agent.hitl.policy import is_mcp_execution_tool, is_sensitive_call
from src.agent.tool_sets import merge_mcp_tools, resolve_tools, should_include_mcp_tools


@tool
def mock_pentest_execute(session_id: str, command: str) -> str:
    """Mock pentest MCP execute."""
    return "ok"


@tool
def mock_think_step(thought: str) -> str:
    """Mock non-sensitive MCP tool."""
    return thought


mock_pentest_execute.name = "pentest_execute"
mock_think_step.name = "sequential-thinking_think"


class TestMergeMcpTools:
    def test_merges_when_toolbox_all(self):
        with (
            patch(
                "src.tools.mcp_client.get_mcp_tools",
                return_value=[mock_pentest_execute],
            ),
            patch(
                "src.config.config_loader.config.get",
                side_effect=lambda k, d=None: (
                    True if k in ("mcp.enabled", "mcp.include_on_all") else d
                ),
            ),
        ):
            base = resolve_tools(["file_ops"], web_search_enabled=False)
            merged = merge_mcp_tools(base, toolbox_names=["all"])
            names = {getattr(t, "name", "") for t in merged}
            assert "pentest_execute" in names
            # Explicit file_ops binds workspace CRUD (lean "all" stays chat-only).
            assert "write_workspace_file" in names
            assert "read_workspace_file" in names
            assert "ingest_github_repo" not in names

    def test_skips_when_mcp_disabled(self):
        with (
            patch("src.config.config_loader.config.get") as mock_get,
            patch(
                "src.tools.mcp_client.get_mcp_tools",
                return_value=[mock_pentest_execute],
            ),
        ):
            mock_get.side_effect = lambda key, default=None: (
                False if key == "mcp.enabled" else default
            )
            tools = merge_mcp_tools([], toolbox_names=["all"])
            assert tools == []

    def test_resolve_tools_all_includes_mcp(self):
        with (
            patch(
                "src.tools.mcp_client.get_mcp_tools",
                return_value=[mock_pentest_execute],
            ),
            patch(
                "src.config.config_loader.config.get",
                side_effect=lambda k, d=None: (
                    True if k in ("mcp.enabled", "mcp.include_on_all") else d
                ),
            ),
        ):
            tools = resolve_tools(["all"])
            assert mock_pentest_execute in tools

    def test_resolve_tools_mcp_only_box(self):
        with patch(
            "src.tools.mcp_client.get_mcp_tools",
            return_value=[mock_pentest_execute],
        ):
            tools = resolve_tools(["mcp"], web_search_enabled=False)
            assert mock_pentest_execute in tools
            assert len(tools) == 2  # ask_user + pentest


class TestMcpHitlPolicy:
    def test_pentest_prefix_sensitive(self):
        assert is_mcp_execution_tool("pentest_execute") is True
        assert (
            is_sensitive_call("pentest_execute", {"command": "nmap localhost"}) is True
        )

    def test_other_mcp_not_auto_sensitive(self):
        assert is_mcp_execution_tool("sequential-thinking_think") is False

    def test_should_include_on_all(self):
        with patch(
            "src.config.config_loader.config.get",
            side_effect=lambda k, d=None: (
                True if k in ("mcp.enabled", "mcp.include_on_all") else d
            ),
        ):
            assert should_include_mcp_tools(["all"]) is True
            assert should_include_mcp_tools(["file_ops"]) is False
            assert should_include_mcp_tools(["mcp"]) is True
