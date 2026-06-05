"""
Global test configuration for Owlynn.

Disables audit log file output for all tests so rotating file I/O does not
cause permission issues in CI or interfere with test assertions.
"""

import os


def pytest_configure(config):
    """Run before test collection — disable audit file logging globabally and sandbox data."""
    os.environ["OWLYNN_AUDIT_LOG_ENABLED"] = "0"
    os.environ.setdefault("OWLYNN_AUDIT_LOG_DIR", "")

    import tempfile
    import pytest
    
    # Sandbox data and workspace dirs globally for all tests
    pytest.test_data_dir = tempfile.TemporaryDirectory(prefix="owlynn_test_data_")
    pytest.test_workspace_dir = tempfile.TemporaryDirectory(prefix="owlynn_test_workspace_")
    
    os.environ["OWLYNN_DATA_DIR"] = pytest.test_data_dir.name
    os.environ["OWLYNN_WORKSPACE_DIR"] = pytest.test_workspace_dir.name

    # Prevent audit_log from setting up file handlers during test imports
    from unittest.mock import patch
    import src.config.audit_log as _audit

    # Disable file logging in the audit module
    _audit._file_logging_enabled = False
