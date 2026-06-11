"""Tests for notebook cell execution timeout and thread isolation."""

import sys
from unittest.mock import MagicMock

sys.modules["mem0"] = MagicMock()

import pytest
from src.tools.notebook import notebook_run, notebook_reset, _reset_notebook
from src.config.audit_log import set_thread_id


@pytest.fixture(autouse=True)
def cleanup():
    _reset_notebook()
    set_thread_id("")
    yield
    _reset_notebook()
    set_thread_id("")


def test_notebook_execution_timeout():
    # It should timeout after 15 seconds, reset session, and return a clear timeout error
    result = notebook_run.invoke({"code": "import time; time.sleep(20)"})
    assert "Timeout Error" in result
    assert "exceeded 15.0 seconds" in result


def test_notebook_session_isolation():
    # Set thread ID A
    set_thread_id("thread_A")
    notebook_run.invoke({"code": "my_val = 12345"})

    # Set thread ID B
    set_thread_id("thread_B")
    res_b = notebook_run.invoke({"code": "print(my_val)"})
    assert "NameError" in res_b or "Error" in res_b
    notebook_run.invoke({"code": "my_val = 67890"})

    # Check thread ID A still has its original value
    set_thread_id("thread_A")
    res_a = notebook_run.invoke({"code": "print(my_val)"})
    assert "12345" in res_a
    assert "67890" not in res_a

    # Clean up both sessions
    notebook_reset.invoke({})
    set_thread_id("thread_B")
    notebook_reset.invoke({})
