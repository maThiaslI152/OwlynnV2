"""Tests for recursion limit configuration and validation."""

import sys
from unittest.mock import MagicMock

sys.modules["mem0"] = MagicMock()

import pytest
from langgraph.checkpoint.memory import MemorySaver

from src.agent.core.graph import build_graph
from src.config.config_loader import config


def test_recursion_limit_configured():
    # Verify the defaults value is loaded correctly
    val = config.get("complex.recursion_limit")
    assert val == 100


def test_graph_accepts_recursion_limit_config():
    compiled = build_graph().compile(checkpointer=MemorySaver())
    config_dict = {
        "configurable": {"thread_id": "test_thread"},
        "recursion_limit": 100,
    }
    # Check that state retrieval works with the config containing recursion_limit
    state = compiled.get_state(config_dict)
    assert state is not None
