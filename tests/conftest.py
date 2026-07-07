"""
Global test configuration for Owlynn.

Disables audit log file output for all tests so rotating file I/O does not
cause permission issues in CI or interfere with test assertions.
"""

import os
import pytest


def pytest_configure(config):
    """Run before test collection — disable audit file logging globabally and sandbox data."""
    os.environ["OWLYNN_AUDIT_LOG_ENABLED"] = "0"
    os.environ.setdefault("OWLYNN_AUDIT_LOG_DIR", "")
    os.environ["OWLYNN_TESTING"] = "1"
    os.environ["OWLYNN_NO_PRELOAD"] = "1"

    import tempfile
    import pytest

    # Sandbox data and workspace dirs globally for all tests
    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "master")
    pytest.test_data_dir = tempfile.TemporaryDirectory(
        prefix=f"owlynn_test_data_{worker_id}_"
    )
    pytest.test_workspace_dir = tempfile.TemporaryDirectory(
        prefix=f"owlynn_test_workspace_{worker_id}_"
    )

    os.environ["OWLYNN_DATA_DIR"] = pytest.test_data_dir.name
    os.environ["OWLYNN_WORKSPACE_DIR"] = pytest.test_workspace_dir.name

    # Set up a unique file-based SQLite database for this test process/worker
    from pathlib import Path

    db_path = Path(tempfile.gettempdir()) / f"owlynn_test_{os.getpid()}.db"
    if db_path.exists():
        try:
            db_path.unlink()
        except OSError:
            pass
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"

    # Prevent audit_log from setting up file handlers during test imports
    from unittest.mock import patch
    import src.config.audit_log as _audit

    # Disable file logging in the audit module
    _audit._file_logging_enabled = False

    # Hypothesis: default no deadline (avoids flaky DeadlineExceeded under xdist/CI load)
    try:
        from hypothesis import settings as hypothesis_settings

        hypothesis_settings.register_profile("owlynn", deadline=None)
        hypothesis_settings.load_profile("owlynn")
    except ImportError:
        pass

    # Globally patch generate_chat_title_router_llm to avoid LM Studio calls in tests
    import src.agent.routing.router as router_mod

    async def fake_title(user_text: str, *args, **kwargs):
        import re

        fallback = user_text.split("\n")[0].strip()
        fallback = re.sub(
            r"^(hi|hey|hello|ok|okay|yes|no|thanks|please)[,.\s]*",
            "",
            fallback,
            flags=re.IGNORECASE,
        ).strip()
        if not fallback:
            return "Mocked Chat Title"
        return fallback[:60]

    fake_title._original = router_mod.generate_chat_title_router_llm
    router_mod.generate_chat_title_router_llm = fake_title


@pytest.fixture(scope="session", autouse=True)
def setup_database_schema():
    """Autouse fixture to programmatically initialize DB schema for tests."""
    import asyncio
    from src.models.base import Base
    from src.models.db import engine

    # Explicitly import all models to ensure they are registered with Base.metadata
    # This prevents 'no such table' errors when xdist workers run subsets of tests
    import src.models.project
    import src.memory.scenarios

    async def _create_tables():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        import nest_asyncio

        nest_asyncio.apply()
        loop.run_until_complete(_create_tables())
    else:
        loop.run_until_complete(_create_tables())
